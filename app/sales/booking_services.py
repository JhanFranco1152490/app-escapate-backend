"""Preparar las solicitudes de reserva de una venta y llevar el estado de cada reserva."""

from datetime import date
from typing import Annotated

from fastapi import Request
from pydantic import AfterValidator, BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.common.errors import NotFound
from app.common.fields import RecordId, optional_multiline_text, optional_text
from app.common.pagination import Page, PageParams, paginate
from app.common.schemas import InputSchema, OutputSchema
from app.quotes.models import QuoteItem
from app.sales.booking_models import Booking, BookingStatus
from app.sales.models import Sale
from app.suppliers.service_types import ServiceType


class BookingUpdate(InputSchema):
    status: BookingStatus
    confirmation_code: Annotated[str, AfterValidator(optional_text(60))] | None = None
    notes: Annotated[str, AfterValidator(optional_multiline_text(2000))] | None = None


class BookingFilters(BaseModel):
    status: BookingStatus | None = None
    sale_id: RecordId | None = None


class BookingSupplierRef(OutputSchema):
    id: int
    trade_name: str
    contact_email: str | None
    contact_phone: str | None


class BookingSaleRef(OutputSchema):
    id: int
    code: str
    destination: str


class BookingOut(OutputSchema):
    id: int
    sale: BookingSaleRef
    supplier: BookingSupplierRef | None
    service_type: ServiceType
    name: str
    details: str | None
    start_date: date | None
    end_date: date | None
    quantity: int
    status: BookingStatus
    confirmation_code: str | None
    notes: str | None


def _options():
    return [joinedload(Booking.sale), joinedload(Booking.supplier)]


def list_bookings(
    session: Session, filters: BookingFilters, params: PageParams, request: Request
) -> Page:
    statement = select(Booking)
    if filters.status is not None:
        statement = statement.where(col(Booking.status) == filters.status)
    if filters.sale_id is not None:
        statement = statement.where(col(Booking.sale_id) == filters.sale_id)
    statement = statement.options(*_options()).order_by(
        col(Booking.start_date).asc().nulls_last(), col(Booking.id)
    )
    return paginate(session, statement, params, request)


def prepare(session: Session, sale_id: int) -> list[Booking]:
    """Crea una reserva por cada servicio incluido de la cotización vendida, sin los opcionales
    ni las alternativas que no se eligieron (no suman al precio de la venta). Repetirlo no
    duplica nada: solo agrega los que falten."""
    sale = session.get(Sale, sale_id)
    if sale is None:
        raise NotFound()
    items = session.exec(
        select(QuoteItem).where(
            QuoteItem.quote_id == sale.quote_id,
            ~col(QuoteItem.is_optional),
            col(QuoteItem.alternative_of_id).is_(None),
        )
    ).all()
    for item in items:
        session.exec(
            insert(Booking)
            .values(
                sale_id=sale.id,
                quote_item_id=item.id,
                supplier_id=item.supplier_id,
                service_type=item.service_type,
                name=item.name,
                details=item.details,
                start_date=item.start_date,
                end_date=item.end_date,
                quantity=item.quantity,
                status=BookingStatus.TO_REQUEST,
            )
            .on_conflict_do_nothing(constraint="uq_booking_quote_item")
        )
    session.commit()
    return list(
        session.exec(
            select(Booking)
            .where(Booking.sale_id == sale.id)
            .options(*_options())
            .order_by(col(Booking.id))
        ).all()
    )


def update(session: Session, booking_id: int, data: BookingUpdate) -> Booking:
    booking = session.get(Booking, booking_id, options=_options())
    if booking is None:
        raise NotFound()
    for name, value in data.model_dump().items():
        setattr(booking, name, value)
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return booking
