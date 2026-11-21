"""Paquetes turísticos: alta, edición, sus servicios y cotizar desde uno.

Cotizar desde un paquete crea la cotización de la solicitud y le copia los servicios, el %
por defecto y la tasa del paquete en una sola transacción. El paquete no cambia.
"""

from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.common.errors import InvalidFields, NotFound, StaleVersion
from app.common.pagination import Page, PageParams, paginate
from app.common.search import has_every_word
from app.quotes.models import Quote, QuoteItem
from app.quotes.package_models import PackageItem, TourPackage
from app.quotes.package_schemas import (
    PackageCreate,
    PackageFilters,
    PackageUpdate,
    QuoteFromPackage,
)
from app.quotes.schemas import QuoteItemCreate, QuoteItemInput, QuoteItemUpdate
from app.quotes.services.quote_items import check_references
from app.quotes.services.quote_management import start_quote
from app.quotes.services.quote_queries import get_quote

NO_ALTERNATIVES = "Un paquete no tiene alternativas: agrega el servicio como incluido u opcional."
INACTIVE_PACKAGE = "El paquete está inactivo."

_ITEM_FIELDS = (
    "service_type",
    "tourist_service_id",
    "supplier_id",
    "name",
    "details",
    "quantity",
    "charge_unit",
    "is_optional",
    "currency",
    "unit_cost",
    "markup_percent",
    "sale_price_override",
    "supplier_commission_percent",
)


def get_package(session: Session, package_id: int) -> TourPackage:
    package = session.get(
        TourPackage,
        package_id,
        options=[
            joinedload(TourPackage.created_by),
            selectinload(TourPackage.items).options(
                joinedload(PackageItem.supplier), joinedload(PackageItem.tourist_service)
            ),
        ],
    )
    if package is None:
        raise NotFound()
    return package


def list_packages(
    session: Session, filters: PackageFilters, params: PageParams, request: Request
) -> Page:
    statement = select(TourPackage)
    if filters.q:
        statement = statement.where(
            or_(
                has_every_word(col(TourPackage.name), filters.q),
                has_every_word(col(TourPackage.destination), filters.q),
            )
        )
    if filters.active is not None:
        statement = statement.where(col(TourPackage.is_active) == filters.active)
    statement = statement.order_by(col(TourPackage.name), col(TourPackage.id))
    return paginate(session, statement, params, request)


def create_package(session: Session, actor: UserAccount, data: PackageCreate) -> TourPackage:
    package = TourPackage(created_by_id=actor.id, **data.model_dump())
    session.add(package)
    session.commit()
    return get_package(session, package.id)


def update_package(session: Session, package_id: int, data: PackageUpdate) -> TourPackage:
    package = get_package(session, package_id)
    if data.expected_version != package.version:
        raise StaleVersion()
    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(package, name, value)
    session.add(package)
    session.commit()
    return get_package(session, package.id)


def _item_values(
    session: Session, package: TourPackage, data: QuoteItemInput, current=None
) -> dict:
    if data.alternative_of_id is not None:
        raise InvalidFields(fields={"alternative_of_id": [NO_ALTERNATIVES]})
    supplier_id = check_references(session, 0, data, current=current)
    values = {name: getattr(data, name) for name in _ITEM_FIELDS}
    values["supplier_id"] = supplier_id
    if values["markup_percent"] is None:
        values["markup_percent"] = package.default_markup_percent
    return values


def _package_item(session: Session, package_id: int, item_id: int) -> PackageItem:
    item = session.get(PackageItem, item_id)
    if item is None or item.package_id != package_id:
        raise NotFound()
    return item


def add_item(session: Session, package_id: int, data: QuoteItemCreate) -> PackageItem:
    package = get_package(session, package_id)
    item = PackageItem(package_id=package.id, **_item_values(session, package, data))
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def update_item(
    session: Session, package_id: int, item_id: int, data: QuoteItemUpdate
) -> PackageItem:
    package = get_package(session, package_id)
    item = _package_item(session, package_id, item_id)
    if data.expected_version != item.version:
        raise StaleVersion()
    for name, value in _item_values(session, package, data, current=item).items():
        setattr(item, name, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def remove_item(session: Session, package_id: int, item_id: int) -> None:
    session.delete(_package_item(session, package_id, item_id))
    session.commit()


def quote_from_package(session: Session, actor: UserAccount, data: QuoteFromPackage) -> Quote:
    package = session.get(TourPackage, data.package_id)
    if package is None:
        raise InvalidFields(fields={"package_id": ["El paquete no existe."]})
    if not package.is_active:
        raise InvalidFields(fields={"package_id": [INACTIVE_PACKAGE]})
    quote = start_quote(session, actor, data.travel_request_id)
    quote.default_markup_percent = package.default_markup_percent
    quote.exchange_rate = package.exchange_rate
    quote.notes = f"Armada desde el paquete {package.code} ({package.name})."
    items = session.exec(
        select(PackageItem).where(PackageItem.package_id == package.id).order_by(PackageItem.id)
    ).all()
    for item in items:
        session.add(
            QuoteItem(quote_id=quote.id, **{name: getattr(item, name) for name in _ITEM_FIELDS})
        )
    session.add(quote)
    session.commit()
    return get_quote(session, quote.id)
