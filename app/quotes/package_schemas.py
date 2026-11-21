from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.common.fields import RecordId, SearchText, optional_multiline_text, required_text
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.quotes.schemas import ExchangeRate, Markup, QuoteItemOut, QuoteTotals


class PackageInput(InputSchema):
    name: Annotated[str, AfterValidator(required_text(150))]
    destination: Annotated[str, AfterValidator(required_text(150))]
    description: Annotated[str, AfterValidator(optional_multiline_text(4000))] | None = None
    nights: int = Field(ge=0, le=365)
    reference_travelers: int = Field(ge=1, le=99)
    default_markup_percent: Markup = Decimal("15.00")
    exchange_rate: ExchangeRate | None = None
    is_active: bool = True


class PackageCreate(PackageInput):
    pass


class PackageUpdate(PackageInput):
    expected_version: int = Field(ge=1)


class PackageFilters(BaseModel):
    q: SearchText = ""
    active: bool | None = None


class PackageListItem(OutputSchema):
    id: int
    code: str
    name: str
    destination: str
    nights: int
    reference_travelers: int
    is_active: bool
    updated_at: datetime


class PackageDetail(PackageListItem):
    description: str | None
    default_markup_percent: Decimal
    exchange_rate: Decimal | None
    created_by: UserRef
    version: int
    items: list[QuoteItemOut]
    totals: QuoteTotals


class QuoteFromPackage(InputSchema):
    travel_request_id: RecordId
    package_id: RecordId
