"""Carga del paquete, las cotizaciones y los seguimientos de demostración. Va después de las
solicitudes, los proveedores y los servicios de demostración: los busca por su documento, su
nombre o su cliente y destino. Todo pasa por los servicios de la aplicación, para respetar sus
reglas (una cotización se envía con servicios, se acepta enviada, etc.).

Repetible: un paquete con el mismo nombre se omite, y también una solicitud que ya tiene
cotización o que alguien cerró a mano en el entorno compartido.
"""

from datetime import timedelta
from functools import partial

from sqlalchemy import exists
from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.common.seeding import SeededRecord, same_document, seed_if_new
from app.quotes.demo_data import DEMO_PACKAGES, DEMO_QUOTES, DemoItem, DemoPackage, DemoQuote
from app.quotes.follow_up_schemas import FollowUpComplete, FollowUpCreate
from app.quotes.models import Quote, QuoteStatus
from app.quotes.package_models import TourPackage
from app.quotes.package_schemas import PackageCreate, QuoteFromPackage
from app.quotes.schemas import (
    QuoteConditionsUpdate,
    QuoteCreate,
    QuoteGeneralUpdate,
    QuoteItemCreate,
    QuoteTransition,
)
from app.quotes.services import follow_ups, packages, quote_items, quote_management
from app.suppliers.models import Supplier
from app.suppliers.tourist_service_models import TouristService
from app.travel_requests.models import TravelRequest, TravelRequestStatus
from app.travel_requests.services.demo_travel_requests import find_demo_request


def _item_input(session: Session, demo: DemoItem) -> QuoteItemCreate:
    references: dict[str, int | None] = {}
    if demo.supplier_document is not None:
        supplier_id = session.exec(
            select(Supplier.id).where(same_document(Supplier, *demo.supplier_document))
        ).one()
        references["supplier_id"] = supplier_id
        if demo.service_name is not None:
            references["tourist_service_id"] = session.exec(
                select(TouristService.id).where(
                    TouristService.supplier_id == supplier_id,
                    TouristService.name == demo.service_name,
                )
            ).one()
    day = today()
    dates = {
        name: day + timedelta(days=days)
        for name, days in (("start_date", demo.start_in), ("end_date", demo.end_in))
        if days is not None
    }
    return QuoteItemCreate(**demo.fields, **references, **dates)


def _create_package(session: Session, actor: UserAccount, demo: DemoPackage) -> None:
    package = packages.create_package(session, actor, PackageCreate(**demo.fields))
    for item in demo.items:
        packages.add_item(session, package.id, _item_input(session, item))


def seed_demo_packages(session: Session, actor: UserAccount) -> list[SeededRecord]:
    return [
        seed_if_new(
            session,
            TourPackage,
            "Paquete",
            demo.fields["name"],
            TourPackage.name == demo.fields["name"],
            partial(_create_package, session, actor, demo),
        )
        for demo in DEMO_PACKAGES
    ]


def _set_dates(session: Session, quote: Quote, demo: DemoQuote) -> Quote:
    day = today()
    dates = {name: day + timedelta(days=days) for name, days in demo.days_from_today.items()}
    general = {
        name: getattr(quote, name)
        for name in ("destination", "origin", "adults", "minors", "valid_until", "notes")
    }
    return quote_management.update_general(
        session,
        quote.id,
        QuoteGeneralUpdate(**general, **dates, expected_version=quote.version),
    )


def _schedule_follow_ups(session: Session, actor: UserAccount, quote: Quote, demo: DemoQuote):
    for demo_follow_up in demo.follow_ups:
        follow_up = follow_ups.schedule(
            session,
            actor,
            quote.id,
            FollowUpCreate(
                due_date=today() + timedelta(days=demo_follow_up.due_in),
                channel=demo_follow_up.channel,
                purpose=demo_follow_up.purpose,
            ),
        )
        if demo_follow_up.outcome is not None:
            follow_ups.complete(
                session, actor, follow_up.id, FollowUpComplete(outcome=demo_follow_up.outcome)
            )


def _create_quote(
    session: Session, actor: UserAccount, request: TravelRequest, demo: DemoQuote
) -> None:
    if demo.package_name is not None:
        package_id = session.exec(
            select(TourPackage.id).where(TourPackage.name == demo.package_name)
        ).one()
        quote = packages.quote_from_package(
            session,
            actor,
            QuoteFromPackage(travel_request_id=request.id, package_id=package_id),
        )
    else:
        quote = quote_management.create_quote(
            session, actor, QuoteCreate(travel_request_id=request.id)
        )
    for item in demo.items:
        quote_items.add_item(session, quote.id, _item_input(session, item))
    if demo.days_from_today:
        quote = _set_dates(session, quote, demo)
    if demo.conditions:
        quote = quote_management.update_conditions(
            session,
            quote.id,
            QuoteConditionsUpdate(**demo.conditions, expected_version=quote.version),
        )
    # Antes de decidir: una cotización aceptada ya no recibe seguimientos.
    _schedule_follow_ups(session, actor, quote, demo)
    if demo.status == QuoteStatus.DRAFT:
        return
    quote = quote_management.send_quote(
        session, quote.id, QuoteTransition(expected_version=quote.version)
    )
    if demo.status == QuoteStatus.ACCEPTED:
        quote_management.accept_quote(
            session, quote.id, QuoteTransition(expected_version=quote.version)
        )


def seed_demo_quotes(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = []
    for demo in DEMO_QUOTES:
        request = find_demo_request(session, demo.client_document, demo.destination)
        # Quien la arma es el asesor responsable de la solicitud.
        advisor = session.get(UserAccount, request.assigned_to_id) or actor
        already_done = exists().where(Quote.travel_request_id == TravelRequest.id) | (
            TravelRequest.status == TravelRequestStatus.CLOSED
        )
        records.append(
            seed_if_new(
                session,
                TravelRequest,
                "Cotización",
                f"{demo.destination} ({request.client.display_name})",
                (TravelRequest.id == request.id) & already_done,
                partial(_create_quote, session, advisor, request, demo),
            )
        )
    return records


def find_demo_quote(session: Session, client_document: tuple[str, str], destination: str):
    """La primera cotización de la solicitud de demostración, la que creó la carga."""
    request = find_demo_request(session, client_document, destination)
    return session.exec(
        select(Quote).where(Quote.travel_request_id == request.id).order_by(Quote.id)
    ).first()
