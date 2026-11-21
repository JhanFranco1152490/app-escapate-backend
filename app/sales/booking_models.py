"""Las reservas de los servicios de una venta.

Preparar las solicitudes de reserva copia cada servicio incluido de la cotización vendida: la
reserva guarda su propia copia, así cambiarla no toca la cotización.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Text, UniqueConstraint, func
from sqlmodel import Field, Relationship, SQLModel

from app.common.columns import foreign_key, in_values, primary_key, timestamp
from app.sales.models import Sale
from app.suppliers.models import Supplier
from app.suppliers.service_types import ServiceType


class BookingStatus(StrEnum):
    # Preparada, todavía no se le pidió al proveedor.
    TO_REQUEST = "to_request"
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Booking(SQLModel, table=True):
    __tablename__ = "booking"
    __table_args__ = (
        CheckConstraint(in_values("status", BookingStatus), name="ck_booking_status"),
        CheckConstraint(in_values("service_type", ServiceType), name="ck_booking_type"),
        # Un servicio de la cotización se prepara una sola vez.
        UniqueConstraint("sale_id", "quote_item_id", name="uq_booking_quote_item"),
    )

    id: int | None = primary_key()
    sale_id: int = foreign_key("sale.id", ondelete="RESTRICT", index=True)
    quote_item_id: int = foreign_key("quote_item.id", ondelete="RESTRICT")
    supplier_id: int | None = foreign_key("supplier.id", ondelete="RESTRICT", nullable=True)
    service_type: str = Field(max_length=20)
    name: str = Field(max_length=150)
    details: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    start_date: date | None = None
    end_date: date | None = None
    quantity: int
    status: str = Field(default=BookingStatus.TO_REQUEST, max_length=12, index=True)
    confirmation_code: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())

    sale: Sale = Relationship()
    supplier: Supplier | None = Relationship()
