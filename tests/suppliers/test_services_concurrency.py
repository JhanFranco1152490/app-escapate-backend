"""Corren con conexiones reales y datos confirmados: lo que se prueba solo ocurre entre
transacciones distintas, así que el rollback de las demás pruebas no sirve aquí."""

import threading
from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.suppliers.errors import ServiceInactive, SupplierInactive
from app.suppliers.models import Supplier
from app.suppliers.rate_schemas import ServiceRateCreate
from app.suppliers.services import rate_management, tourist_service_management
from app.suppliers.tourist_service_models import ServiceRate, TouristService
from app.suppliers.tourist_service_schemas import TouristServiceCreate, TouristServiceUpdate
from tests.concurrency import wait_until_blocked
from tests.factories import SupplierFactory, TouristServiceFactory, UserAccountFactory, use_session

SERVICE = {
    "service_type": "lodging",
    "name": "Habitación familiar",
    "destination": "Cartagena",
    "attributes": {"lodging_kind": "hotel", "max_capacity": 4},
}
RATE = {
    "name": "Temporada alta",
    "valid_from": "2026-12-15",
    "currency": "COP",
    "charge_unit": "per_night",
    "amount": "710000",
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
        mine = col(Supplier.created_by_id) == manager_id
        services = select(TouristService.id).join(Supplier).where(mine)
        cleanup.exec(delete(ServiceRate).where(col(ServiceRate.tourist_service_id).in_(services)))
        cleanup.exec(delete(TouristService).where(col(TouristService.id).in_(services)))
        cleanup.exec(delete(Supplier).where(mine))
        cleanup.exec(delete(UserAccount).where(col(UserAccount.id) == manager_id))
        cleanup.commit()


def _committed(engine, manager_id: int, build: Callable) -> int:
    with Session(engine) as setup:
        use_session(setup)
        record_id = build(setup.get(UserAccount, manager_id)).id
        setup.commit()
        use_session(None)
    return record_id


def _deactivate(record, actor: UserAccount) -> None:
    record.is_active = False
    record.deactivated_at = datetime.now(timezone.utc)
    record.deactivated_by = actor


def _in_a_thread(target: Callable[[], None]) -> tuple[threading.Thread, dict]:
    outcome: dict[str, BaseException | None] = {}

    def run() -> None:
        try:
            target()
            outcome["error"] = None
        except BaseException as error:  # noqa: BLE001
            outcome["error"] = error

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def test_two_people_saving_the_same_service_at_once(engine, manager_id):
    service_id = _committed(
        engine, manager_id, lambda manager: TouristServiceFactory(supplier__created_by=manager)
    )

    with Session(engine) as first, Session(engine) as second:
        # La segunda petición ya revisó la versión (1) y está por guardar; justo entonces la
        # primera guarda.
        stale = second.get(TouristService, service_id)
        assert stale.version == 1
        tourist_service_management.update_tourist_service(
            first, service_id, TouristServiceUpdate(**SERVICE, expected_version=1)
        )

        stale.destination = "San Andrés"
        with pytest.raises(StaleDataError):
            second.commit()

    with Session(engine) as check:
        saved = check.get(TouristService, service_id)
        assert (saved.destination, saved.version) == ("Cartagena", 2)


def test_a_service_registered_while_its_supplier_is_deactivated(engine, manager_id):
    supplier_id = _committed(
        engine, manager_id, lambda manager: SupplierFactory(created_by=manager)
    )

    def register() -> None:
        with Session(engine) as session:
            actor = session.get(UserAccount, manager_id)
            tourist_service_management.create_tourist_service(
                session, actor, supplier_id, TouristServiceCreate(**SERVICE)
            )

    with Session(engine) as holder:
        # Otra petición está desactivando el proveedor y todavía no confirma.
        _deactivate(holder.get(Supplier, supplier_id), holder.get(UserAccount, manager_id))
        holder.flush()
        thread, outcome = _in_a_thread(register)
        wait_until_blocked(engine, waiting=1)
        holder.commit()

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert isinstance(outcome["error"], SupplierInactive)
    with Session(engine) as check:
        statement = select(TouristService.id).where(TouristService.supplier_id == supplier_id)
        assert check.exec(statement).all() == []


def test_a_rate_registered_while_its_service_is_deactivated(engine, manager_id):
    service_id = _committed(
        engine, manager_id, lambda manager: TouristServiceFactory(supplier__created_by=manager)
    )

    def register() -> None:
        with Session(engine) as session:
            actor = session.get(UserAccount, manager_id)
            rate_management.create_service_rate(
                session, actor, service_id, ServiceRateCreate(**RATE)
            )

    with Session(engine) as holder:
        _deactivate(holder.get(TouristService, service_id), holder.get(UserAccount, manager_id))
        holder.flush()
        thread, outcome = _in_a_thread(register)
        wait_until_blocked(engine, waiting=1)
        holder.commit()

    thread.join(timeout=10)

    assert not thread.is_alive()
    assert isinstance(outcome["error"], ServiceInactive)
    with Session(engine) as check:
        statement = select(ServiceRate.id).where(ServiceRate.tourist_service_id == service_id)
        assert check.exec(statement).all() == []
