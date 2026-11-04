from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY
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


class SupplierCategory(StrEnum):
    """Lo que vende el proveedor. Es la misma lista de tipos de servicio, para que la oferta
    se pueda filtrar por categoría sin texto libre. El orden es el de las pantallas."""

    LODGING = "lodging"
    AIR = "air"
    GROUND = "ground"
    TOURS = "tours"
    CRUISE = "cruise"
    FOOD = "food"
    WHOLESALER = "wholesaler"
    OTHER = "other"


class SupplierDocumentType(StrEnum):
    NIT = "NIT"
    CC = "CC"
    CE = "CE"
    FOREIGN = "FOREIGN"


_CATEGORIES = ", ".join(f"'{member.value}'" for member in SupplierCategory)


class Supplier(SQLModel, table=True):
    __tablename__ = "supplier"
    __table_args__ = (
        CheckConstraint(
            in_values("document_type", SupplierDocumentType), name="ck_supplier_document_type"
        ),
        CheckConstraint(
            "(document_type IS NULL) = (document_number IS NULL)",
            name="ck_supplier_document_pair",
        ),
        CheckConstraint(
            f"cardinality(categories) >= 1 AND categories <@ ARRAY[{_CATEGORIES}]::varchar[]",
            name="ck_supplier_categories",
        ),
        CheckConstraint(
            "contact_phone IS NOT NULL OR contact_email IS NOT NULL", name="ck_supplier_contact"
        ),
        CheckConstraint("commission_rate BETWEEN 0 AND 100", name="ck_supplier_commission_rate"),
        CheckConstraint("is_active = (deactivated_at IS NULL)", name="ck_supplier_deactivated_at"),
        CheckConstraint(
            "(deactivated_at IS NULL) = (deactivated_by_id IS NULL)",
            name="ck_supplier_deactivated_by",
        ),
        # El documento es opcional: solo se repite la pareja cuando sí se registró.
        Index(
            "uq_supplier_document",
            "document_type",
            "document_number",
            unique=True,
            postgresql_where=text("document_number IS NOT NULL"),
        ),
    )

    id: int | None = primary_key()
    trade_name: str = Field(max_length=150)
    legal_name: str | None = Field(default=None, max_length=150)
    document_type: str | None = Field(default=None, max_length=10)
    document_number: str | None = Field(default=None, max_length=30)
    # Códigos de SupplierCategory. Un arreglo y no una tabla aparte: es una lista fija que
    # siempre se lee junto con el proveedor.
    categories: list[str] = Field(sa_column=Column(ARRAY(String(20)), nullable=False))
    city: str | None = Field(default=None, max_length=80)
    coverage_zone: str | None = Field(default=None, max_length=150)
    contact_name: str = Field(max_length=150)
    contact_role: str | None = Field(default=None, max_length=80)
    # E.164: "+" y hasta 15 dígitos.
    contact_phone: str | None = Field(default=None, max_length=16)
    contact_email: str | None = Field(default=None, max_length=254)
    payment_terms: str | None = Field(default=None, max_length=500)
    # Porcentaje de referencia; no entra en ningún cálculo.
    commission_rate: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    agreement_valid_until: date | None = None
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": true()})
    deactivated_at: datetime | None = timestamp(nullable=True)
    deactivated_by_id: int | None = foreign_key(
        "user_account.id", ondelete="RESTRICT", nullable=True
    )
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    created_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Supplier.created_by_id]"}
    )
    deactivated_by: UserAccount | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Supplier.deactivated_by_id]"}
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    @property
    def agreement_expired(self) -> bool:
        # Vence al terminar el día de la vigencia, en Bogotá.
        return self.agreement_valid_until is not None and self.agreement_valid_until < today()
