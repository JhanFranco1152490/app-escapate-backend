"""Corren con conexiones reales y datos confirmados: lo que se prueba solo ocurre entre
transacciones distintas, así que el rollback de las demás pruebas no sirve aquí."""

import threading

import pytest
from sqlalchemy import delete
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.clients.errors import DuplicateClient
from app.clients.models import Client
from app.clients.schemas import ClientCreate, ClientUpdate
from app.clients.services import client_management, client_queries
from tests.concurrency import wait_until_blocked
from tests.factories import ClientFactory, UserAccountFactory, use_session

PERSON = {
    "client_type": "person",
    "first_name": "Marcela",
    "last_name": "Gómez Ortiz",
    "document_type": "CC",
    "document_number": "1020304050",
    "phone": "3001112233",
    "contact_source": "instagram",
}


@pytest.fixture
def advisor_id(engine):
    with Session(engine) as setup:
        use_session(setup)
        advisor = UserAccountFactory()
        setup.commit()
        advisor_id = advisor.id
        use_session(None)
    yield advisor_id
    with Session(engine) as cleanup:
        cleanup.exec(delete(Client).where(col(Client.created_by_id) == advisor_id))
        cleanup.exec(delete(UserAccount).where(col(UserAccount.id) == advisor_id))
        cleanup.commit()


def test_two_people_saving_the_same_client_at_once(engine, advisor_id):
    with Session(engine) as setup:
        use_session(setup)
        client_id = ClientFactory(created_by=setup.get(UserAccount, advisor_id), **PERSON).id
        setup.commit()
        use_session(None)

    with Session(engine) as first, Session(engine) as second:
        # La segunda petición ya revisó la versión (1) y está por guardar, como dentro de
        # update_client entre la revisión y el commit; justo entonces la primera guarda.
        stale = client_queries.get_client(second, client_id)
        assert stale.version == 1
        client_management.update_client(
            first, client_id, ClientUpdate(**PERSON, city="Cúcuta", expected_version=1)
        )

        stale.city = "Bogotá"
        with pytest.raises(StaleDataError):
            second.commit()

    with Session(engine) as check:
        saved = check.get(Client, client_id)
        assert (saved.city, saved.version) == ("Cúcuta", 2)


def test_two_clients_with_the_same_document_at_once(engine, advisor_id):
    outcome: dict[str, BaseException | None] = {}

    def register() -> None:
        with Session(engine) as session:
            try:
                actor = session.get(UserAccount, advisor_id)
                client_management.create_client(
                    session, actor, ClientCreate(**PERSON, data_consent=True)
                )
                outcome["error"] = None
            except BaseException as error:  # noqa: BLE001
                outcome["error"] = error

    with Session(engine) as holder:
        use_session(holder)
        # Otra petición insertó el mismo documento y todavía no confirma: la revisión de
        # la segunda no lo ve, y su INSERT queda esperando el índice único.
        ClientFactory(created_by=holder.get(UserAccount, advisor_id), **PERSON)
        holder.flush()
        thread = threading.Thread(target=register)
        thread.start()
        wait_until_blocked(engine, waiting=1)
        holder.commit()
        use_session(None)

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert isinstance(outcome["error"], DuplicateClient)
    with Session(engine) as check:
        count = len(check.exec(select(Client.id).where(Client.created_by_id == advisor_id)).all())
        assert count == 1
