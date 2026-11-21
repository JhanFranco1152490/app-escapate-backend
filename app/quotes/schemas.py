from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.common.fields import (
    RecordId,
    SearchText,
    optional_multiline_text,
    optional_text,
    required_text,
)
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.quotes.models import QuoteStatus
from app.suppliers.service_types import ChargeUnit, Currency, ServiceType

MAX_AMOUNT = Decimal("999999999999")
MAX_PESOS = 999_999_999_999

Destination = Annotated[str, AfterValidator(required_text(150))]
Origin = Annotated[str, AfterValidator(optional_text(120))]
LongText = Annotated[str, AfterValidator(optional_multiline_text(4000))]
ItemName = Annotated[str, AfterValidator(required_text(150))]
ItemDetails = Annotated[str, AfterValidator(optional_multiline_text(2000))]
# Un % de recargo: puede pasar de 100 (un servicio barato con un cargo fijo de la agencia).
Markup = Annotated[Decimal, Field(ge=0, le=Decimal("999.99"), max_digits=5, decimal_places=2)]
Percent = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
Commission = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
ExchangeRate = Annotated[
    Decimal, Field(gt=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2)
]
# Estricto: un precio en pesos con decimales o como texto es un error, no se redondea.
Pesos = Annotated[int, Field(strict=True, ge=0, le=MAX_PESOS)]


def _error(kind: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(kind, message)


def _not_before(value: date | None, info: ValidationInfo, start_field: str) -> date | None:
    start = info.data.get(start_field)
    if value is not None and start is not None and value < start:
        raise _error("before_start", "No puede ser anterior a la fecha de inicio.")
    return value


class QuoteCreate(InputSchema):
    travel_request_id: RecordId


class QuoteGeneralUpdate(InputSchema):
    destination: Destination
    origin: Origin | None = None
    departure_date: date | None = None
    return_date: date | None = None
    adults: int = Field(ge=1, le=99)
    minors: int = Field(ge=0, le=99)
    valid_until: date
    notes: LongText | None = None
    expected_version: int = Field(ge=1)

    @field_validator("return_date")
    @classmethod
    def return_after_departure(cls, value: date | None, info: ValidationInfo) -> date | None:
        return _not_before(value, info, "departure_date")


class QuoteConditionsUpdate(InputSchema):
    deposit_percent: Percent | None = None
    balance_due_date: date | None = None
    payment_terms: LongText | None = None
    policies: LongText | None = None
    expected_version: int = Field(ge=1)


class QuotePricingUpdate(InputSchema):
    default_markup_percent: Markup
    exchange_rate: ExchangeRate | None = None
    expected_version: int = Field(ge=1)


class QuoteTransition(InputSchema):
    expected_version: int = Field(ge=1)


class QuoteCopy(InputSchema):
    # Versión: sigue siendo la misma propuesta, corregida (sube el número). Duplicado: una
    # cotización nueva que parte de esta.
    as_new_version: bool = False


class QuoteItemInput(InputSchema):
    # El orden importa: cada validador lee los campos anteriores (`info.data`).
    service_type: ServiceType
    tourist_service_id: RecordId | None = None
    supplier_id: RecordId | None = None
    name: ItemName
    details: ItemDetails | None = None
    start_date: date | None = None
    end_date: date | None = None
    quantity: int = Field(ge=1, le=9999)
    charge_unit: ChargeUnit | None = None
    is_optional: bool = False
    # Otro servicio de la misma cotización del que este es una alternativa.
    alternative_of_id: RecordId | None = None
    currency: Currency
    unit_cost: Decimal = Field(ge=0, le=MAX_AMOUNT, max_digits=14, decimal_places=2)
    # Sin valor, el servicio toma el % por defecto de la cotización.
    markup_percent: Markup | None = None
    sale_price_override: Pesos | None = None
    supplier_commission_percent: Commission | None = None

    @field_validator("end_date")
    @classmethod
    def ends_after_it_starts(cls, value: date | None, info: ValidationInfo) -> date | None:
        return _not_before(value, info, "start_date")

    @field_validator("unit_cost")
    @classmethod
    def whole_pesos(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        if info.data.get("currency") == Currency.COP and value != value.to_integral_value():
            raise _error("cents_in_pesos", "En pesos el valor va sin decimales.")
        return value


class QuoteItemCreate(QuoteItemInput):
    pass


class QuoteItemUpdate(QuoteItemInput):
    expected_version: int = Field(ge=1)


class QuoteStatusFilter(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    # Enviadas con la vigencia vencida.
    EXPIRED = "expired"


class QuoteFilters(BaseModel):
    """Sin `extra="forbid"`: conviven con los parámetros de la paginación."""

    q: SearchText = ""
    status: QuoteStatusFilter | None = None
    client_id: RecordId | None = None
    travel_request_id: RecordId | None = None


class QuoteClientRef(OutputSchema):
    id: int
    display_name: str


class QuoteRequestRef(OutputSchema):
    id: int
    code: str


class QuoteSupplierRef(OutputSchema):
    id: int
    trade_name: str


class QuoteServiceRef(OutputSchema):
    id: int
    name: str


class QuoteListItem(OutputSchema):
    id: int
    code: str
    revision: int
    previous_quote_id: int | None
    status: QuoteStatus
    is_expired: bool
    client: QuoteClientRef
    travel_request: QuoteRequestRef
    destination: str
    departure_date: date | None
    return_date: date | None
    valid_until: date
    created_by: UserRef
    created_at: datetime
    updated_at: datetime


class QuoteItemOut(OutputSchema):
    id: int
    service_type: ServiceType
    tourist_service: QuoteServiceRef | None
    supplier: QuoteSupplierRef | None
    name: str
    details: str | None
    start_date: date | None
    end_date: date | None
    quantity: int
    charge_unit: ChargeUnit | None
    is_optional: bool
    alternative_of_id: int | None
    currency: Currency
    unit_cost: Decimal
    markup_percent: Decimal
    sale_price_override: int | None
    supplier_commission_percent: Decimal | None
    # En pesos; `None` si está en dólares y la cotización no tiene tasa de cambio.
    cost_in_pesos: int | None
    sale_price: int | None
    version: int

    @field_serializer("unit_cost")
    def cost_in_its_currency(self, amount: Decimal) -> str:
        # Texto y no número: en dólares lleva centavos y un número del JSON los podría perder.
        return f"{amount:.0f}" if self.currency == Currency.COP else f"{amount:.2f}"


class QuoteTotals(OutputSchema):
    """Solo los servicios incluidos; los opcionales se suman aparte."""

    cost: int
    sale: int
    profit: int
    margin_percent: Decimal | None
    optional_sale: int
    per_person: int | None
    deposit: int | None
    missing_exchange_rate: bool


class QuoteDetail(QuoteListItem):
    origin: str | None
    adults: int
    minors: int
    notes: str | None
    default_markup_percent: Decimal
    exchange_rate: Decimal | None
    deposit_percent: Decimal | None
    balance_due_date: date | None
    payment_terms: str | None
    policies: str | None
    sent_at: datetime | None
    decided_at: datetime | None
    version: int
    items: list[QuoteItemOut]
    totals: QuoteTotals


class OfferFilters(BaseModel):
    q: SearchText = ""
    service_type: ServiceType | None = None


class OfferRate(OutputSchema):
    id: int
    name: str
    currency: Currency
    charge_unit: ChargeUnit
    amount: Decimal
    valid_from: date
    valid_until: date | None

    @field_serializer("amount")
    def amount_in_its_currency(self, amount: Decimal) -> str:
        return f"{amount:.0f}" if self.currency == Currency.COP else f"{amount:.2f}"


class OfferService(OutputSchema):
    id: int
    service_type: ServiceType
    name: str
    destination: str
    description: str | None
    supplier: QuoteSupplierRef
    rates: list[OfferRate]
