"""Corren con conexiones reales y datos confirmados: lo que se prueba solo ocurre entre
transacciones distintas, así que el rollback de las demás pruebas no sirve aquí."""

import pytest
from sqlalchemy import delete
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, col, select

from app.accounts.models import Role, UserAccount
from app.clients.models import Client
from app.travel_requests.models import TravelRequest
from app.travel_requests.schemas import TravelRequestClose, TravelRequestUpdate
from app.travel_requests.services import request_management, request_queries
from tests.factories import ClientFactory, TravelRequestFactory, UserAccountFactory, use_session


@pytest.fixture
def request_id(engine):
    """Una solicitud nueva confirmada, de un asesor comercial que puede ser responsable."""
    with Session(engine) as setup:
        use_session(setup)
        role = setup.exec(select(Role).where(Role.name == "Asesor comercial")).one()
        advisor = UserAccountFactory(role=role)
        request = TravelRequestFactory(
            client=ClientFactory(created_by=advisor), assigned_to=advisor
        )
        setup.commit()
        ids = (request.id, request.client_id, advisor.id)
        use_session(None)
    yield ids[0]
    with Session(engine) as cleanup:
        cleanup.exec(delete(TravelRequest).where(col(TravelRequest.id) == ids[0]))
        cleanup.exec(delete(Client).where(col(Client.id) == ids[1]))
        cleanup.exec(delete(UserAccount).where(col(UserAccount.id) == ids[2]))
        cleanup.commit()


def _update(request: TravelRequest, **changes) -> TravelRequestUpdate:
    body = {
        "client_id": request.client_id,
        "destination": request.destination,
        "date_mode": request.date_mode,
        "departure_date": request.departure_date,
        "adults": request.adults,
        "minors": request.minors,
        "assigned_to_id": request.assigned_to_id,
        "expected_version": request.version,
    }
    return TravelRequestUpdate(**(body | changes))


def test_two_people_editing_the_same_request_at_once(engine, request_id):
    with Session(engine) as first, Session(engine) as second:
        # La segunda petición ya revisó la versión (1) y está por guardar, como dentro de
        # update_request entre la revisión y el commit; justo entonces la primera guarda.
        stale = request_queries.get_request(second, request_id)
        assert stale.version == 1
        request_management.update_request(
            first, request_id, _update(stale, destination="Cartagena")
        )

        stale.destination = "Santa Marta"
        with pytest.raises(StaleDataError):
            second.commit()

    with Session(engine) as check:
        saved = check.get(TravelRequest, request_id)
        assert (saved.destination, saved.version) == ("Cartagena", 2)


def test_closing_while_someone_edits_keeps_only_the_close(engine, request_id):
    with Session(engine) as closer, Session(engine) as editor:
        stale = request_queries.get_request(editor, request_id)
        actor = closer.get(UserAccount, stale.assigned_to_id)
        request_management.close_request(
            closer,
            actor,
            request_id,
            TravelRequestClose(reason="no_response", expected_version=1),
        )

        stale.minors = 3
        with pytest.raises(StaleDataError):
            editor.commit()

    with Session(engine) as check:
        saved = check.get(TravelRequest, request_id)
        assert (saved.status, saved.minors, saved.version) == ("closed", 0, 2)
