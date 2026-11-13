"""Carga de servicios y tarifas de demostración. Repetible: un servicio que su proveedor ya
tiene con ese nombre se omite junto con sus tarifas, porque las fechas son relativas a hoy y
cargarlas otro día agregaría tarifas nuevas."""

from functools import partial

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.common.seeding import SeededRecord, same_document, seed_if_new
from app.suppliers.demo_data import DEMO_TOURIST_SERVICES, DemoService
from app.suppliers.models import Supplier
from app.suppliers.rate_schemas import ServiceRateCreate
from app.suppliers.services.rate_management import create_service_rate
from app.suppliers.services.tourist_service_management import (
    create_tourist_service,
    deactivate_tourist_service,
)
from app.suppliers.tourist_service_models import TouristService
from app.suppliers.tourist_service_schemas import TouristServiceCreate, TouristServiceStatusChange


def _create(session: Session, actor: UserAccount, supplier_id: int, demo: DemoService) -> None:
    service = create_tourist_service(
        session, actor, supplier_id, TouristServiceCreate(**demo.fields)
    )
    day = today()
    for rate in demo.rates:
        create_service_rate(session, actor, service.id, ServiceRateCreate(**rate.fields(day)))
    # Se desactiva al final: un servicio inactivo ya no recibe tarifas.
    if not demo.active:
        deactivate_tourist_service(
            session,
            actor,
            service.id,
            TouristServiceStatusChange(expected_version=service.version),
        )


def seed_demo_tourist_services(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = []
    for demo in DEMO_TOURIST_SERVICES:
        supplier = session.exec(
            select(Supplier).where(same_document(Supplier, *demo.supplier_document))
        ).one()
        name = demo.fields["name"]
        records.append(
            seed_if_new(
                session,
                TouristService,
                "Servicio",
                f"{name} ({supplier.trade_name})",
                (TouristService.supplier_id == supplier.id) & (TouristService.name == name),
                partial(_create, session, actor, supplier.id, demo),
            )
        )
    return records
