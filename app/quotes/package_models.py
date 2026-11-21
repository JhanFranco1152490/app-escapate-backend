"""Paquetes turísticos: una combinación de servicios reutilizable, con sus precios de
referencia, desde la que se arma una cotización.

Sus servicios tienen la misma forma que los de una cotización (así se copian tal cual y se
calculan con el mismo motor de liquidación), pero sin fechas: el paquete no es un viaje.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.sql import false, true
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.common.codes import RecordCode
from app.common.columns import (
    foreign_key,
    in_values,
    primary_key,
    timestamp,
    version_column,
    versioned,
)
from app.quotes import pricing
from app.quotes.models import QualityLevel
from app.suppliers.models import Supplier
from app.suppliers.service_types import ChargeUnit, Currency, ServiceType
from app.suppliers.tourist_service_models import TouristService

PACKAGE_CODE = RecordCode("PAQ-")


class TourPackage(SQLModel, table=True):
    __tablename__ = "tour_package"
    __table_args__ = (
        CheckConstraint("nights BETWEEN 0 AND 365", name="ck_tour_package_nights"),
        CheckConstraint("reference_travelers BETWEEN 1 AND 99", name="ck_tour_package_travelers"),
        CheckConstraint("default_markup_percent >= 0", name="ck_tour_package_markup"),
        CheckConstraint(
            "exchange_rate IS NULL OR exchange_rate > 0", name="ck_tour_package_exchange"
        ),
    )

    id: int | None = primary_key()
    name: str = Field(max_length=150)
    destination: str = Field(max_length=150)
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    nights: int = Field(sa_column=Column(SmallInteger, nullable=False))
    # Para cuántas personas están pensados los precios (el valor por persona sale de aquí).
    reference_travelers: int = Field(sa_column=Column(SmallInteger, nullable=False))
    default_markup_percent: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    exchange_rate: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(10, 2), nullable=True)
    )
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": true()})
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    created_by: UserAccount = Relationship()
    items: list["PackageItem"] = Relationship(
        back_populates="package",
        sa_relationship_kwargs={"order_by": "PackageItem.id", "viewonly": True},
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    @property
    def code(self) -> str:
        return PACKAGE_CODE.format(self.id)

    @property
    def totals(self) -> pricing.Totals:
        lines = [
            pricing.LineAmounts(item.cost_in_pesos, item.sale_price, item.is_optional)
            for item in self.items
        ]
        return pricing.totals(lines, self.reference_travelers, None)


class PackageItem(SQLModel, table=True):
    __tablename__ = "package_item"
    __table_args__ = (
        CheckConstraint(in_values("service_type", ServiceType), name="ck_package_item_type"),
        CheckConstraint(in_values("currency", Currency), name="ck_package_item_currency"),
        CheckConstraint(
            in_values("quality_level", QualityLevel), name="ck_package_item_quality_level"
        ),
        CheckConstraint(in_values("charge_unit", ChargeUnit), name="ck_package_item_charge_unit"),
        CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_package_item_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_package_item_unit_cost"),
        CheckConstraint(
            "currency <> 'COP' OR unit_cost = trunc(unit_cost)",
            name="ck_package_item_whole_pesos",
        ),
        CheckConstraint("markup_percent >= 0", name="ck_package_item_markup"),
    )

    id: int | None = primary_key()
    package_id: int = foreign_key("tour_package.id", ondelete="CASCADE", index=True)
    service_type: str = Field(max_length=20)
    tourist_service_id: int | None = foreign_key(
        "tourist_service.id", ondelete="RESTRICT", nullable=True
    )
    supplier_id: int | None = foreign_key("supplier.id", ondelete="RESTRICT", nullable=True)
    name: str = Field(max_length=150)
    details: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    quantity: int = Field(sa_column=Column(Integer, nullable=False))
    charge_unit: str | None = Field(default=None, max_length=30)
    is_optional: bool = Field(default=False, sa_column_kwargs={"server_default": false()})
    quality_level: str | None = Field(default=None, max_length=10)
    currency: str = Field(sa_column=Column(CHAR(3), nullable=False))
    unit_cost: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    markup_percent: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    sale_price_override: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    supplier_commission_percent: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    package: TourPackage = Relationship(back_populates="items")
    tourist_service: TouristService | None = Relationship()
    supplier: Supplier | None = Relationship()

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    # El paquete no tiene fechas ni alternativas: se responden vacías para que sus servicios
    # tengan la misma forma que los de una cotización.
    @property
    def start_date(self) -> None:
        return None

    @property
    def end_date(self) -> None:
        return None

    @property
    def alternative_of_id(self) -> None:
        return None

    @property
    def cost_in_pesos(self) -> int | None:
        return pricing.cost_in_pesos(
            self.unit_cost, self.quantity, self.currency, self.package.exchange_rate
        )

    @property
    def sale_price(self) -> int | None:
        return pricing.sale_price(
            self.cost_in_pesos, self.markup_percent, self.sale_price_override
        )
