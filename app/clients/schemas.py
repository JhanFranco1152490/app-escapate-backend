from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.clients.models import (
    PERSON_DOCUMENT_TYPES,
    ClientDocumentType,
    ClientType,
    ContactSource,
    TravelerDocumentType,
)
from app.common.countries import COUNTRY_CODES
from app.common.dates import today
from app.common.fields import (
    NAME_MAX_LENGTH,
    City,
    Email,
    InternationalPhone,
    PersonName,
    RecordId,
    SearchText,
    optional_text,
    valid_document_number,
)
from app.common.identifiers import normalize_document
from app.common.schemas import InputSchema, OutputSchema, UserRef

OLDEST_BIRTH_DATE = date(1900, 1, 1)

_REQUIRED = "Este campo es obligatorio."
_NOT_FOR_PERSON = "No aplica para una persona."
_NOT_FOR_COMPANY = "No aplica para una empresa."


def _error(kind: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(kind, message)


def _past_date(value: date) -> date:
    if value > today():
        raise _error("future_date", "La fecha no puede ser futura.")
    if value < OLDEST_BIRTH_DATE:
        raise _error("too_old", "Revisa el año.")
    return value


def _country(value: str) -> str:
    code = value.strip().upper()
    if code not in COUNTRY_CODES:
        raise _error("invalid_country", "No es un país válido.")
    return code


PastDate = Annotated[date, AfterValidator(_past_date)]
CountryCode = Annotated[str, AfterValidator(_country)]
# Opcionales en el esquema: si son obligatorios depende del tipo de cliente.
OptionalName = Annotated[str, AfterValidator(optional_text(NAME_MAX_LENGTH))]
BusinessName = Annotated[str, AfterValidator(optional_text(150))]
ContactDetail = Annotated[str, AfterValidator(optional_text(120))]
ClientNotes = Annotated[str, AfterValidator(optional_text(2000))]
TravelerNotes = Annotated[str, AfterValidator(optional_text(1000))]


def _depends_on_type():
    # Se valida aunque no venga: así un campo obligatorio para el tipo de cliente que falta
    # se informa en su propio campo, junto con los demás errores.
    return Field(default=None, validate_default=True)


def _confirmed(value: bool | None, message: str) -> bool:
    if value is not True:
        raise _error("consent_required", message)
    return value


class ClientInput(InputSchema):
    # El orden importa: cada validador lee los campos anteriores (`info.data`).
    client_type: ClientType
    first_name: OptionalName | None = _depends_on_type()
    last_name: OptionalName | None = _depends_on_type()
    business_name: BusinessName | None = _depends_on_type()
    document_type: ClientDocumentType | None = _depends_on_type()
    document_number: str | None = _depends_on_type()
    birth_date: PastDate | None = _depends_on_type()
    phone: InternationalPhone
    email: Email | None = None
    city: City | None = None
    contact_source: ContactSource
    contact_source_detail: ContactDetail | None = _depends_on_type()
    notes: ClientNotes | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def names_only_for_people(cls, value: str | None, info: ValidationInfo) -> str | None:
        client_type = info.data.get("client_type")
        if client_type == ClientType.PERSON and value is None:
            raise _error("required", _REQUIRED)
        if client_type == ClientType.COMPANY and value is not None:
            raise _error("not_applicable", _NOT_FOR_COMPANY)
        return value

    @field_validator("business_name")
    @classmethod
    def business_name_only_for_companies(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        client_type = info.data.get("client_type")
        if client_type == ClientType.COMPANY and value is None:
            raise _error("required", _REQUIRED)
        if client_type == ClientType.PERSON and value is not None:
            raise _error("not_applicable", _NOT_FOR_PERSON)
        return value

    @field_validator("birth_date")
    @classmethod
    def birth_date_only_for_people(cls, value: date | None, info: ValidationInfo) -> date | None:
        if info.data.get("client_type") == ClientType.COMPANY and value is not None:
            raise _error("not_applicable", _NOT_FOR_COMPANY)
        return value

    @field_validator("document_type")
    @classmethod
    def document_type_matches_the_client(
        cls, value: ClientDocumentType | None, info: ValidationInfo
    ) -> ClientDocumentType | None:
        client_type = info.data.get("client_type")
        if value is None:
            return value
        if client_type == ClientType.PERSON and value not in PERSON_DOCUMENT_TYPES:
            raise _error("invalid_document_type", "Una persona se registra con CC, CE, PPT o PA.")
        if client_type == ClientType.COMPANY and value != ClientDocumentType.NIT:
            raise _error("invalid_document_type", "Una empresa se registra con NIT.")
        return value

    @field_validator("document_number")
    @classmethod
    def document_number_goes_with_its_type(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        number = None if value is None or not value.strip() else value
        if "document_type" not in info.data:
            # El tipo ya falló: ese es el error que se informa; aquí solo se normaliza.
            return normalize_document(number) if number else None
        document_type = info.data["document_type"]
        if document_type is None and number is None:
            return None
        if number is None:
            raise _error("required", "Indica también el número.")
        if document_type is None:
            raise _error("required", "Elige también el tipo de documento.")
        return valid_document_number(document_type, number)

    @field_validator("contact_source_detail")
    @classmethod
    def other_needs_its_detail(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("contact_source") == ContactSource.OTHER and value is None:
            raise _error("required", "Cuéntanos cuál.")
        return value


class ClientCreate(ClientInput):
    data_consent: bool | None = _depends_on_type()

    @field_validator("data_consent")
    @classmethod
    def consent_is_confirmed(cls, value: bool | None) -> bool:
        return _confirmed(value, "Confirma que el cliente autorizó el tratamiento de sus datos.")


class ClientUpdate(ClientInput):
    # La autorización solo se registra al crear: editar no la cambia.
    expected_version: int = Field(ge=1)


class TravelerInput(InputSchema):
    first_name: PersonName
    last_name: PersonName
    document_type: TravelerDocumentType
    document_number: str
    birth_date: PastDate
    nationality: CountryCode
    reference_client_id: RecordId | None = None
    is_the_client: bool = False
    notes: TravelerNotes | None = None

    @field_validator("document_number")
    @classmethod
    def document_number_is_valid_for_its_type(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise _error("required", _REQUIRED)
        document_type = info.data.get("document_type")
        if document_type is None:
            return normalize_document(value)
        return valid_document_number(document_type, value)

    @field_validator("is_the_client")
    @classmethod
    def the_client_must_be_chosen(cls, value: bool, info: ValidationInfo) -> bool:
        # Si el id ya falló, ese es el error que se informa.
        if value and "reference_client_id" in info.data and not info.data["reference_client_id"]:
            raise _error(
                "reference_client_required", "Elige primero el cliente que también viaja."
            )
        return value


class TravelerCreate(TravelerInput):
    data_consent: bool | None = _depends_on_type()

    @field_validator("data_consent")
    @classmethod
    def consent_is_confirmed(cls, value: bool | None) -> bool:
        return _confirmed(
            value,
            "Confirma que el viajero, o su representante legal si es menor de edad, autorizó "
            "el tratamiento de sus datos.",
        )


class TravelerUpdate(TravelerInput):
    expected_version: int = Field(ge=1)


class ClientFilters(BaseModel):
    """Sin `extra="forbid"`: conviven con los parámetros de la paginación."""

    q: SearchText = ""
    client_type: ClientType | None = None


class TravelerFilters(BaseModel):
    q: SearchText = ""
    client_id: RecordId | None = None


class ClientListItem(OutputSchema):
    id: int
    client_type: ClientType
    display_name: str
    email: str | None
    phone: str
    document_type: ClientDocumentType | None
    document_number: str | None
    city: str | None


class ClientDetail(ClientListItem):
    first_name: str | None
    last_name: str | None
    business_name: str | None
    birth_date: date | None
    contact_source: ContactSource
    contact_source_detail: str | None
    notes: str | None
    data_consent_at: datetime
    data_consent_by: UserRef
    created_by: UserRef
    created_at: datetime
    updated_at: datetime
    version: int


class ReferenceClient(OutputSchema):
    id: int
    display_name: str


class TravelerListItem(OutputSchema):
    id: int
    first_name: str
    last_name: str
    full_name: str
    document_type: TravelerDocumentType
    document_number: str
    birth_date: date
    age: int
    is_minor: bool
    nationality: str
    reference_client: ReferenceClient | None
    is_the_client: bool


class TravelerDetail(TravelerListItem):
    notes: str | None
    data_consent_at: datetime
    data_consent_by: UserRef
    created_by: UserRef
    created_at: datetime
    updated_at: datetime
    version: int
