from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.common.fields import (
    City,
    Email,
    InternationalPhone,
    SearchText,
    optional_document_number,
    optional_text,
    required_text,
)
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.suppliers.models import SupplierCategory, SupplierDocumentType

_CATEGORY_CODES = tuple(member.value for member in SupplierCategory)
_CONTACT_FIELDS = ("contact_phone", "contact_email")
_CONTACT_REQUIRED = "Indica un teléfono o un correo de contacto."


def _known_categories(value: Any) -> Any:
    # Antes de convertir a enum: Pydantic marcaría el error en la posición de la lista
    # ("categories.1") y el formulario no sabría en qué campo mostrarlo.
    if isinstance(value, list) and any(item not in _CATEGORY_CODES for item in value):
        raise PydanticCustomError("invalid_category", "No es una clasificación válida.")
    return value


def _ordered_categories(value: list[SupplierCategory]) -> list[SupplierCategory]:
    if not value:
        raise PydanticCustomError("required", "Elige al menos una clasificación.")
    if len(set(value)) != len(value):
        raise PydanticCustomError("repeated_category", "Hay una clasificación repetida.")
    return sorted(value, key=_CATEGORY_CODES.index)


def _blank_as_none(value: Any) -> Any:
    # Un campo de contacto vacío es un campo sin llenar, no un teléfono o correo inválido.
    return None if isinstance(value, str) and not value.strip() else value


def _is_filled(value: Any) -> bool:
    return value is not None and _blank_as_none(value) is not None


def _contact_required(field: str) -> InitErrorDetails:
    return InitErrorDetails(
        type=PydanticCustomError("contact_required", _CONTACT_REQUIRED), loc=(field,), input=None
    )


def _same_error(error: dict) -> InitErrorDetails:
    # from_exception_data no reconoce por nombre los tipos de error propios del proyecto.
    return InitErrorDetails(
        type=PydanticCustomError(error["type"], error["msg"]),
        loc=error["loc"],
        input=error["input"],
    )


TradeName = Annotated[str, AfterValidator(required_text(150))]
ContactName = Annotated[str, AfterValidator(required_text(150))]
LegalName = Annotated[str, AfterValidator(optional_text(150))]
CoverageZone = Annotated[str, AfterValidator(optional_text(150))]
ContactRole = Annotated[str, AfterValidator(optional_text(80))]
PaymentTerms = Annotated[str, AfterValidator(optional_text(500))]
SupplierNotes = Annotated[str, AfterValidator(optional_text(2000))]
Categories = Annotated[
    list[SupplierCategory],
    Field(max_length=len(SupplierCategory)),
    BeforeValidator(_known_categories),
    AfterValidator(_ordered_categories),
]
ContactPhone = Annotated[InternationalPhone | None, BeforeValidator(_blank_as_none)]
ContactEmail = Annotated[Email | None, BeforeValidator(_blank_as_none)]


class SupplierInput(InputSchema):
    trade_name: TradeName
    legal_name: LegalName | None = None
    document_type: SupplierDocumentType | None = None
    document_number: str | None = Field(default=None, validate_default=True)
    categories: Categories
    city: City | None = None
    coverage_zone: CoverageZone | None = None
    contact_name: ContactName
    contact_role: ContactRole | None = None
    contact_phone: ContactPhone = None
    contact_email: ContactEmail = None
    payment_terms: PaymentTerms | None = None
    commission_rate: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    agreement_valid_until: date | None = None
    notes: SupplierNotes | None = None

    @field_validator("document_number")
    @classmethod
    def document_number_goes_with_its_type(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        return optional_document_number(value, info)

    @model_validator(mode="wrap")
    @classmethod
    def phone_or_email(cls, data: Any, handler):
        # Un validador de campo solo ve los campos anteriores: el del teléfono no sabría si
        # hay correo. Aquí se mira el cuerpo completo, y el error va en los dos campos y junto
        # con los demás errores del cuerpo.
        missing = isinstance(data, dict) and not any(
            _is_filled(data.get(field)) for field in _CONTACT_FIELDS
        )
        contact_errors = [_contact_required(field) for field in _CONTACT_FIELDS] if missing else []
        try:
            supplier = handler(data)
        except ValidationError as error:
            if not contact_errors:
                raise
            raise ValidationError.from_exception_data(
                cls.__name__, [*map(_same_error, error.errors()), *contact_errors]
            ) from None
        if contact_errors:
            raise ValidationError.from_exception_data(cls.__name__, contact_errors)
        return supplier


class SupplierCreate(SupplierInput):
    pass


class SupplierUpdate(SupplierInput):
    expected_version: int = Field(ge=1)


class SupplierStatusChange(InputSchema):
    expected_version: int = Field(ge=1)


class SupplierStatusFilter(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ALL = "all"


class SupplierFilters(BaseModel):
    """Sin `extra="forbid"`: conviven con los parámetros de la paginación."""

    q: SearchText = ""
    category: SupplierCategory | None = None
    status: SupplierStatusFilter = SupplierStatusFilter.ACTIVE


class SupplierListItem(OutputSchema):
    id: int
    trade_name: str
    legal_name: str | None
    document_type: SupplierDocumentType | None
    document_number: str | None
    categories: list[SupplierCategory]
    city: str | None
    contact_name: str
    contact_email: str | None
    contact_phone: str | None
    is_active: bool


class SupplierDetail(SupplierListItem):
    coverage_zone: str | None
    contact_role: str | None
    payment_terms: str | None
    commission_rate: Decimal | None
    agreement_valid_until: date | None
    agreement_expired: bool
    notes: str | None
    deactivated_at: datetime | None
    deactivated_by: UserRef | None
    created_by: UserRef
    created_at: datetime
    updated_at: datetime
    version: int
