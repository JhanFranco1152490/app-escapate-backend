from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.common.fields import (
    RecordId,
    SearchText,
    optional_multiline_text,
    optional_text,
)
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.sales.models import PaymentMethod, PaymentStatus

Pesos = Annotated[int, Field(strict=True, ge=1, le=999_999_999_999)]


class SaleCreate(InputSchema):
    quote_id: RecordId
    # Sin valor, el precio de los servicios incluidos de la cotización. Con valor, el que se
    # acordó (por ejemplo, si el cliente sumó opcionales).
    total_price: Pesos | None = None
    notes: Annotated[str, AfterValidator(optional_multiline_text(2000))] | None = None


class PaymentCreate(InputSchema):
    amount: Pesos
    paid_on: date
    method: PaymentMethod
    reference: Annotated[str, AfterValidator(optional_text(100))] | None = None
    notes: Annotated[str, AfterValidator(optional_text(500))] | None = None


class SaleFilters(BaseModel):
    q: SearchText = ""
    payment_status: PaymentStatus | None = None
    quote_id: RecordId | None = None
    client_id: RecordId | None = None


class SaleClientRef(OutputSchema):
    id: int
    display_name: str


class SaleQuoteRef(OutputSchema):
    id: int
    code: str


class PaymentOut(OutputSchema):
    id: int
    amount: int
    paid_on: date
    method: PaymentMethod
    reference: str | None
    notes: str | None
    created_by: UserRef
    created_at: datetime


class SaleListItem(OutputSchema):
    id: int
    code: str
    quote: SaleQuoteRef
    client: SaleClientRef
    destination: str
    departure_date: date | None
    return_date: date | None
    total_price: int
    paid: int
    balance: int
    payment_status: PaymentStatus
    created_at: datetime


class SaleDetail(SaleListItem):
    adults: int
    minors: int
    total_cost: int
    notes: str | None
    created_by: UserRef
    payments: list[PaymentOut]
