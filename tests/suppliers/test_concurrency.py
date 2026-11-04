"""Corren con conexiones reales y datos confirmados: lo que se prueba solo ocurre entre
transacciones distintas, así que el rollback de las demás pruebas no sirve aquí."""

import threading

import pytest
from sqlalchemy import delete
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.suppliers.errors import DuplicateSupplier
from app.suppliers.models import Supplier
from app.suppliers.schemas import SupplierCreate, SupplierUpdate
from app.suppliers.services import supplier_management, supplier_queries
from tests.concurrency import wait_until_blocked
from tests.factories import SupplierFactory, UserAccountFactory, use_session

HOTEL = {
    "trade_name": "Hotel Caribe Azul",
    "document_type": "NIT",
    "document_number": "8001972684",
    "categories": ["lodging"],
    "contact_name": "Andrea Pérez",
    "contact_phone": "+573001112233",
}


@pytest.fixture
def manager_id(engine):
    with Session(engine) as setup:
        use_session(setup)
        manager = UserAccountFactory()
        setup.commit()
        manager_id = manager.id
        use_session(None)
    yield manager_id
    with Session(engine) as cleanup:
        cleanup.exec(delete(Supplier).where(col(Supplier.created_by_id) == manager_id))
        cleanup.exec(delete(UserAccount).where(col(UserAccount.id) == manager_id))
        cleanup.commit()


def test_two_people_saving_the_same_supplier_at_once(engine, manager_id):
    with Session(engine) as setup:
        use_session(setup)
        supplier_id = SupplierFactory(created_by=setup.get(UserAccount, manager_id), **HOTEL).id
        setup.commit()
        use_session(None)

    with Session(engine) as first, Session(engine) as second:
        # La segunda petición ya revisó la versión (1) y está por guardar, como dentro de
        # update_supplier entre la revisión y el commit; justo entonces la primera guarda.
        stale = supplier_queries.get_supplier(second, supplier_id)
        assert stale.version == 1
        supplier_management.update_supplier(
            first, supplier_id, SupplierUpdate(**HOTEL, city="Cartagena", expected_version=1)
        )

        stale.city = "Bogotá"
        with pytest.raises(StaleDataError):
            second.commit()

    with Session(engine) as check:
        saved = check.get(Supplier, supplier_id)
        assert (saved.city, saved.version) == ("Cartagena", 2)


def test_two_suppliers_with_the_same_document_at_once(engine, manager_id):
    outcome: dict[str, BaseException | None] = {}

    def register() -> None:
        with Session(engine) as session:
            try:
                actor = session.get(UserAccount, manager_id)
                supplier_management.create_supplier(session, actor, SupplierCreate(**HOTEL))
                outcome["error"] = None
            except BaseException as error:  # noqa: BLE001
                outcome["error"] = error

    with Session(engine) as holder:
        use_session(holder)
        # Otra petición insertó el mismo documento y todavía no confirma: la revisión de
        # la segunda no lo ve, y su INSERT queda esperando el índice único.
        SupplierFactory(created_by=holder.get(UserAccount, manager_id), **HOTEL)
        holder.flush()
        thread = threading.Thread(target=register)
        thread.start()
        wait_until_blocked(engine, waiting=1)
        holder.commit()
        use_session(None)

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert isinstance(outcome["error"], DuplicateSupplier)
    with Session(engine) as check:
        statement = select(Supplier.id).where(Supplier.created_by_id == manager_id)
        assert len(check.exec(statement).all()) == 1
