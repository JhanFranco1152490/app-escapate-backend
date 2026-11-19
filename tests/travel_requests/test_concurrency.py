"""Corren con conexiones reales y datos confirmados: lo que se prueba solo ocurre entre
transacciones distintas, así que el rollback de las demás pruebas no sirve aquí."""

import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, col, select

from app.accounts.models import Role, UserAccount
from app.clients.models import Client, Traveler
from app.travel_requests.errors import TravelRequestClosed
from app.travel_requests.models import TravelRequest, TravelRequestTraveler
from app.travel_requests.schemas import (
    RequestTravelersAdd,
    TravelRequestClose,
    TravelRequestUpdate,
)
from app.travel_requests.services import request_management, request_queries, request_travelers
from tests.concurrency import wait_until_blocked
from tests.factories import (
    ClientFactory,
    TravelerFactory,
    TravelRequestFactory,
    UserAccountFactory,
    use_session,
)


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


# --- Viajeros de la solicitud ----------------------------------------------------------------


@pytest.fixture
def traveler_id(engine, request_id):
    """Un viajero confirmado. Al terminar borra también sus asociaciones, antes de que
    `request_id` borre la solicitud."""
    with Session(engine) as setup:
        use_session(setup)
        request = setup.get(TravelRequest, request_id)
        traveler = TravelerFactory(created_by=setup.get(UserAccount, request.created_by_id))
        setup.commit()
        new_id = traveler.id
        use_session(None)
    yield new_id
    with Session(engine) as cleanup:
        cleanup.exec(
            delete(TravelRequestTraveler).where(col(TravelRequestTraveler.traveler_id) == new_id)
        )
        cleanup.exec(delete(Traveler).where(col(Traveler.id) == new_id))
        cleanup.commit()


def _in_background(engine, target) -> tuple[threading.Thread, dict]:
    """Corre `target(session)` en otra conexión y guarda el error que lance (o None)."""
    outcome: dict[str, BaseException | None] = {}

    def run() -> None:
        with Session(engine) as session:
            try:
                target(session)
                outcome["error"] = None
            except BaseException as error:  # noqa: BLE001
                outcome["error"] = error

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _add(request_id: int, traveler_id: int):
    def add(session: Session) -> None:
        request = session.get(TravelRequest, request_id)
        actor = session.get(UserAccount, request.assigned_to_id)
        request_travelers.add_travelers(
            session, actor, request_id, RequestTravelersAdd(traveler_ids=[traveler_id])
        )

    return add


def _hold_an_association(session: Session, request_id: int, traveler_id: int) -> None:
    """Lo que hace add_travelers hasta antes de su commit: la solicitud leída con FOR SHARE
    y la fila insertada, sin confirmar."""
    request = session.exec(
        select(TravelRequest).where(TravelRequest.id == request_id).with_for_update(read=True)
    ).one()
    session.exec(
        insert(TravelRequestTraveler).values(
            travel_request_id=request_id,
            traveler_id=traveler_id,
            added_by_id=request.assigned_to_id,
        )
    )


def _links(engine, request_id: int) -> list[TravelRequestTraveler]:
    with Session(engine) as check:
        return check.exec(
            select(TravelRequestTraveler).where(
                TravelRequestTraveler.travel_request_id == request_id
            )
        ).all()


def test_two_people_associating_the_same_traveler_at_once(engine, request_id, traveler_id):
    with Session(engine) as first:
        # La primera asociación insertó la fila y no confirma: la segunda espera en la llave
        # de la tabla puente, no en la solicitud (FOR SHARE no bloquea a otro FOR SHARE).
        _hold_an_association(first, request_id, traveler_id)
        thread, outcome = _in_background(engine, _add(request_id, traveler_id))
        wait_until_blocked(engine, waiting=1)
        first.commit()

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert outcome["error"] is None
    assert len(_links(engine, request_id)) == 1


def test_associating_while_someone_closes_the_request_is_rejected(engine, request_id, traveler_id):
    with Session(engine) as closer:
        # El cierre ya escribió la fila de la solicitud y no confirma: la asociación espera en
        # su FOR SHARE y, al seguir, ve la solicitud cerrada.
        request = closer.get(TravelRequest, request_id)
        request.status = "closed"
        request.close_reason = "no_response"
        request.closed_by_id = request.assigned_to_id
        request.closed_at = datetime.now(timezone.utc)
        closer.flush()
        thread, outcome = _in_background(engine, _add(request_id, traveler_id))
        wait_until_blocked(engine, waiting=1)
        closer.commit()

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert isinstance(outcome["error"], TravelRequestClosed)
    assert _links(engine, request_id) == []


def test_closing_while_someone_associates_waits_and_keeps_the_traveler(
    engine, request_id, traveler_id
):
    def close(session: Session) -> None:
        request = session.get(TravelRequest, request_id)
        actor = session.get(UserAccount, request.assigned_to_id)
        request_management.close_request(
            session,
            actor,
            request_id,
            TravelRequestClose(reason="no_response", expected_version=request.version),
        )

    with Session(engine) as first:
        # La asociación tiene la solicitud con FOR SHARE: el cierre espera a que confirme.
        _hold_an_association(first, request_id, traveler_id)
        thread, outcome = _in_background(engine, close)
        wait_until_blocked(engine, waiting=1)
        first.commit()

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert outcome["error"] is None
    with Session(engine) as check:
        assert check.get(TravelRequest, request_id).status == "closed"
    assert [link.traveler_id for link in _links(engine, request_id)] == [traveler_id]
