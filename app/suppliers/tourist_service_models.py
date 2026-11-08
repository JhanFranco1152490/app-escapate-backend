"""Servicios turísticos de un proveedor y sus tarifas.

Van aparte de `models.py` porque usan las listas fijas de `service_types.py`, que a su vez
importa de `models.py` la clasificación del proveedor.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CHAR, CheckConstraint, Column, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlalchemy.sql import true
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.common.columns import (
    foreign_key,
    in_values,
    primary_key,
    timestamp,
    version_column,
    versioned,
)
from app.common.dates import today
from app.suppliers.models import Supplier
from app.suppliers.service_types import ChargeUnit, Currency, ServiceType


class RateValidity(StrEnum):
    UPCOMING = "upcoming"
    CURRENT = "current"
    EXPIRED = "expired"


def validity_status(valid_from: date, valid_until: date | None, day: date) -> RateValidity:
    """Una tarifa vale desde su primer día hasta el último, los dos incluidos. Sin fecha
    final vale indefinidamente."""
    if valid_from > day:
        return RateValidity.UPCOMING
    if valid_until is not None and valid_until < day:
        return RateValidity.EXPIRED
    return RateValidity.CURRENT


class TouristService(SQLModel, table=True):
    __tablename__ = "tourist_service"
    __table_args__ = (
        CheckConstraint(in_values("service_type", ServiceType), name="ck_tourist_service_type"),
        # La forma de los atributos depende del tipo y la valida la API; la base solo asegura
        # que sea un objeto.
        CheckConstraint(
            "jsonb_typeof(attributes) = 'object'", name="ck_tourist_service_attributes"
        ),
        CheckConstraint(
            "is_active = (deactivated_at IS NULL)", name="ck_tourist_service_deactivated_at"
        ),
        CheckConstraint(
            "(deactivated_at IS NULL) = (deactivated_by_id IS NULL)",
            name="ck_tourist_service_deactivated_by",
        ),
    )

    id: int | None = primary_key()
    supplier_id: int = foreign_key("supplier.id", ondelete="RESTRICT", index=True)
    service_type: str = Field(max_length=20)
    name: str = Field(max_length=150)
    destination: str = Field(max_length=120)
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    conditions: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Se reemplaza entero al editar, nunca se modifica en su lugar: SQLAlchemy no detecta los
    # cambios dentro de un dict y no los guardaría.
    attributes: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": true()})
    deactivated_at: datetime | None = timestamp(nullable=True)
    deactivated_by_id: int | None = foreign_key(
        "user_account.id", ondelete="RESTRICT", nullable=True
    )
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    supplier: Supplier = Relationship()
    created_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[TouristService.created_by_id]"}
    )
    deactivated_by: UserAccount | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[TouristService.deactivated_by_id]"}
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)


class ServiceRate(SQLModel, table=True):
    __tablename__ = "service_rate"
    __table_args__ = (
        CheckConstraint(in_values("currency", Currency), name="ck_service_rate_currency"),
        CheckConstraint(in_values("charge_unit", ChargeUnit), name="ck_service_rate_charge_unit"),
        CheckConstraint("amount > 0", name="ck_service_rate_amount"),
        # Los pesos van enteros; solo los dólares traen centavos.
        CheckConstraint(
            "currency <> 'COP' OR amount = trunc(amount)", name="ck_service_rate_whole_pesos"
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from", name="ck_service_rate_validity"
        ),
    )

    id: int | None = primary_key()
    tourist_service_id: int = foreign_key("tourist_service.id", ondelete="RESTRICT", index=True)
    name: str = Field(max_length=100)
    valid_from: date
    valid_until: date | None = None
    currency: str = Field(sa_column=Column(CHAR(3), nullable=False))
    charge_unit: str = Field(max_length=30)
    # El valor tal como lo da el proveedor, en su moneda: no se convierte ni se redondea aquí.
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    conditions: str | None = Field(default=None, max_length=1000)
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    tourist_service: TouristService = Relationship()
    created_by: UserAccount = Relationship()

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    @property
    def validity_status(self) -> RateValidity:
        return validity_status(self.valid_from, self.valid_until, today())
