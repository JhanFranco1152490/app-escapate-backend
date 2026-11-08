from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, ValidationInfo, field_serializer, field_validator
from pydantic_core import PydanticCustomError

from app.common.fields import optional_text, required_text
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.suppliers.service_types import ChargeUnit, Currency
from app.suppliers.tourist_service_models import RateValidity

RateName = Annotated[str, AfterValidator(required_text(100))]
RateConditions = Annotated[str, AfterValidator(optional_text(1000))]


class ServiceRateInput(InputSchema):
    # El orden importa: cada validador de campo solo ve los campos declarados antes.
    name: RateName
    valid_from: date
    valid_until: date | None = None
    currency: Currency
    charge_unit: ChargeUnit
    amount: Decimal = Field(gt=0, le=Decimal("999999999999"), max_digits=14, decimal_places=2)
    conditions: RateConditions | None = None

    @field_validator("valid_until")
    @classmethod
    def ends_after_it_starts(cls, value: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("valid_from")
        if value is not None and start is not None and value < start:
            raise PydanticCustomError(
                "ends_before_start", "La fecha final no puede ser anterior a la inicial."
            )
        return value

    @field_validator("amount")
    @classmethod
    def whole_pesos(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        # Un proveedor que cobra en pesos da el valor entero; solo los dólares traen centavos.
        if info.data.get("currency") == Currency.COP and value != value.to_integral_value():
            raise PydanticCustomError("cents_in_pesos", "En pesos el valor va sin decimales.")
        return value


class ServiceRateCreate(ServiceRateInput):
    pass


class ServiceRateUpdate(ServiceRateInput):
    expected_version: int = Field(ge=1)


class ServiceRate(OutputSchema):
    id: int
    name: str
    valid_from: date
    valid_until: date | None
    currency: Currency
    charge_unit: ChargeUnit
    amount: Decimal
    conditions: str | None
    validity_status: RateValidity
    created_by: UserRef
    created_at: datetime
    updated_at: datetime
    version: int

    @field_serializer("amount")
    def amount_in_its_currency(self, amount: Decimal) -> str:
        # Texto y no número: en dólares lleva centavos y un número del JSON los podría perder.
        return f"{amount:.0f}" if self.currency == Currency.COP else f"{amount:.2f}"
