"""La cotización (`Quote`) y sus servicios (`QuoteItem`).

La cotización nace de una solicitud de viaje y copia sus datos generales: desde ahí se edita
por su cuenta, sin tocar la solicitud. Los servicios pueden salir del catálogo de un
proveedor o escribirse a mano (el asesor también cotiza con proveedores que no están
registrados).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

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
from sqlalchemy.sql import false
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.common.codes import RecordCode
from app.common.columns import (
    foreign_key,
    in_values,
    primary_key,
    timestamp,
    version_column,
    versioned,
)
from app.common.dates import today
from app.quotes import pricing
from app.suppliers.models import Supplier
from app.suppliers.service_types import ChargeUnit, Currency, ServiceType
from app.suppliers.tourist_service_models import TouristService
from app.travel_requests.models import TravelRequest

QUOTE_CODE = RecordCode("COT-")


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# Ya se le presentó al cliente: tiene fecha de envío.
PRESENTED_STATUSES = (QuoteStatus.SENT, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED)
DECIDED_STATUSES = (QuoteStatus.ACCEPTED, QuoteStatus.REJECTED)


def _status_list(statuses: tuple[QuoteStatus, ...]) -> str:
    return ", ".join(f"'{status.value}'" for status in statuses)


class Quote(SQLModel, table=True):
    __tablename__ = "quote"
    __table_args__ = (
        CheckConstraint(in_values("status", QuoteStatus), name="ck_quote_status"),
        CheckConstraint(
            "return_date IS NULL OR departure_date IS NULL OR return_date >= departure_date",
            name="ck_quote_dates",
        ),
        CheckConstraint("adults BETWEEN 1 AND 99", name="ck_quote_adults"),
        CheckConstraint("minors BETWEEN 0 AND 99", name="ck_quote_minors"),
        CheckConstraint("default_markup_percent >= 0", name="ck_quote_default_markup"),
        CheckConstraint("exchange_rate IS NULL OR exchange_rate > 0", name="ck_quote_exchange"),
        CheckConstraint(
            "deposit_percent IS NULL OR (deposit_percent > 0 AND deposit_percent <= 100)",
            name="ck_quote_deposit",
        ),
        CheckConstraint(
            f"(status IN ({_status_list(PRESENTED_STATUSES)})) = (sent_at IS NOT NULL)",
            name="ck_quote_sent_at",
        ),
        CheckConstraint(
            f"(status IN ({_status_list(DECIDED_STATUSES)})) = (decided_at IS NOT NULL)",
            name="ck_quote_decided_at",
        ),
    )

    id: int | None = primary_key()
    travel_request_id: int = foreign_key("travel_request.id", ondelete="RESTRICT", index=True)
    client_id: int = foreign_key("client.id", ondelete="RESTRICT", index=True)
    status: str = Field(default=QuoteStatus.DRAFT, max_length=10, index=True)
    destination: str = Field(max_length=150)
    origin: str | None = Field(default=None, max_length=120)
    departure_date: date | None = None
    return_date: date | None = None
    adults: int = Field(sa_column=Column(SmallInteger, nullable=False))
    minors: int = Field(sa_column=Column(SmallInteger, nullable=False))
    valid_until: date
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # El % que reciben los servicios nuevos; cada servicio puede cambiar el suyo.
    default_markup_percent: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    # Pesos por dólar: la tasa con que se cotizan los servicios en USD.
    exchange_rate: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(10, 2), nullable=True)
    )
    deposit_percent: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    balance_due_date: date | None = None
    payment_terms: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    policies: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    sent_at: datetime | None = timestamp(nullable=True)
    decided_at: datetime | None = timestamp(nullable=True)
    # Una versión nueva apunta a la cotización de la que salió y sube su número.
    previous_quote_id: int | None = foreign_key("quote.id", ondelete="RESTRICT", nullable=True)
    revision: int = Field(
        default=1, sa_column=Column(SmallInteger, nullable=False, server_default="1")
    )
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    travel_request: TravelRequest = Relationship()
    client: Client = Relationship()
    created_by: UserAccount = Relationship()
    items: list["QuoteItem"] = Relationship(
        back_populates="quote",
        sa_relationship_kwargs={"order_by": "QuoteItem.id", "viewonly": True},
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    @property
    def code(self) -> str:
        return QUOTE_CODE.format(self.id)

    @property
    def is_expired(self) -> bool:
        """Enviada y con la vigencia vencida. No se guarda: se calcula con la fecha de
        Bogotá cada vez que se consulta."""
        return self.status == QuoteStatus.SENT and self.valid_until < today()

    @property
    def totals(self) -> pricing.Totals:
        lines = [
            pricing.LineAmounts(
                item.cost_in_pesos,
                item.sale_price,
                item.is_optional,
                item.alternative_of_id is not None,
            )
            for item in self.items
        ]
        return pricing.totals(lines, self.adults + self.minors, self.deposit_percent)


class QuoteItem(SQLModel, table=True):
    __tablename__ = "quote_item"
    __table_args__ = (
        CheckConstraint(in_values("service_type", ServiceType), name="ck_quote_item_type"),
        CheckConstraint(in_values("currency", Currency), name="ck_quote_item_currency"),
        CheckConstraint(in_values("charge_unit", ChargeUnit), name="ck_quote_item_charge_unit"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_quote_item_dates",
        ),
        CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_quote_item_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_quote_item_unit_cost"),
        CheckConstraint(
            "currency <> 'COP' OR unit_cost = trunc(unit_cost)",
            name="ck_quote_item_whole_pesos",
        ),
        CheckConstraint("markup_percent >= 0", name="ck_quote_item_markup"),
        CheckConstraint(
            "sale_price_override IS NULL OR sale_price_override >= 0",
            name="ck_quote_item_override",
        ),
        CheckConstraint(
            "supplier_commission_percent IS NULL "
            "OR supplier_commission_percent BETWEEN 0 AND 100",
            name="ck_quote_item_commission",
        ),
    )

    id: int | None = primary_key()
    quote_id: int = foreign_key("quote.id", ondelete="RESTRICT", index=True)
    service_type: str = Field(max_length=20)
    tourist_service_id: int | None = foreign_key(
        "tourist_service.id", ondelete="RESTRICT", nullable=True
    )
    supplier_id: int | None = foreign_key("supplier.id", ondelete="RESTRICT", nullable=True)
    name: str = Field(max_length=150)
    details: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    start_date: date | None = None
    end_date: date | None = None
    quantity: int = Field(sa_column=Column(Integer, nullable=False))
    charge_unit: str | None = Field(default=None, max_length=30)
    is_optional: bool = Field(default=False, sa_column_kwargs={"server_default": false()})
    # Otra opción para el mismo servicio (otro hotel, otro vuelo): no suma al total, se ofrece
    # al cliente junto al servicio del que es alternativa.
    alternative_of_id: int | None = foreign_key(
        "quote_item.id", ondelete="SET NULL", nullable=True
    )
    currency: str = Field(sa_column=Column(CHAR(3), nullable=False))
    # Lo que cobra el proveedor por unidad, en su moneda: COP en pesos enteros, USD con
    # centavos. La conversión a pesos se hace al calcular el precio, con la tasa de la
    # cotización.
    unit_cost: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    markup_percent: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    # Precio de venta total del servicio escrito por el asesor (por ejemplo, para
    # redondear). Si está, manda sobre el calculado con el %.
    sale_price_override: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    # Solo de referencia: lo que el proveedor le reconoce a la agencia. No entra al precio.
    supplier_commission_percent: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    quote: Quote = Relationship(back_populates="items")
    tourist_service: TouristService | None = Relationship()
    supplier: Supplier | None = Relationship()

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    @property
    def cost_in_pesos(self) -> int | None:
        return pricing.cost_in_pesos(
            self.unit_cost, self.quantity, self.currency, self.quote.exchange_rate
        )

    @property
    def sale_price(self) -> int | None:
        return pricing.sale_price(
            self.cost_in_pesos, self.markup_percent, self.sale_price_override
        )
