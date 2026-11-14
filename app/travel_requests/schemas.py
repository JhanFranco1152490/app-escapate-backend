from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.common.fields import (
    RecordId,
    SearchText,
    fixed_choices,
    optional_multiline_text,
    optional_text,
    required_text,
)
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.travel_requests.models import (
    AccommodationCategory,
    CloseReason,
    DateMode,
    TravelRequestStatus,
    TravelType,
)

MAX_BUDGET = 999_999_999_999

_NOT_FOR_EXACT = "No aplica con fechas exactas."
_NOT_FOR_FLEXIBLE = "No aplica con un período flexible."

Destination = Annotated[str, AfterValidator(required_text(150))]
Origin = Annotated[str, AfterValidator(optional_text(120))]
Notes = Annotated[str, AfterValidator(optional_multiline_text(2000))]
CloseNote = Annotated[str, AfterValidator(optional_text(300))]
# Estricto: 6000000.5 o "6000000" son un error, no un valor que se redondea o se convierte.
Budget = Annotated[int, Field(strict=True, ge=1, le=MAX_BUDGET)]
Nights = Annotated[int, Field(ge=1, le=365)]
TravelTypes = fixed_choices(
    TravelType, unknown="No es un tipo de viaje válido.", repeated="Hay un tipo de viaje repetido."
)


def _error(kind: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(kind, message)


def _depends_on_mode():
    # Se valida aunque no venga: así una fecha obligatoria para el modo elegido que falta se
    # informa en su propio campo, junto con los demás errores.
    return Field(default=None, validate_default=True)


def _check_mode_field(
    value: object, info: ValidationInfo, *, used_with: DateMode, required: str | None = None
) -> bool:
    """Revisa un campo que solo aplica con un modo de fechas. Devuelve si hay que seguir
    revisándolo (si aplica y vino)."""
    mode = info.data.get("date_mode")
    if mode is None:
        # El modo ya falló: ese es el error que se informa.
        return False
    if mode != used_with:
        if value is not None:
            not_applicable = _NOT_FOR_FLEXIBLE if used_with == DateMode.EXACT else _NOT_FOR_EXACT
            raise _error("not_applicable", not_applicable)
        return False
    if value is None:
        if required is not None:
            raise _error("required", required)
        return False
    return True


class TravelRequestInput(InputSchema):
    # El orden importa: cada validador lee los campos anteriores (`info.data`).
    client_id: RecordId
    destination: Destination
    origin: Origin | None = None
    date_mode: DateMode
    departure_date: date | None = _depends_on_mode()
    return_date: date | None = _depends_on_mode()
    window_start: date | None = _depends_on_mode()
    window_end: date | None = _depends_on_mode()
    approx_nights: Nights | None = _depends_on_mode()
    adults: int = Field(ge=1, le=99)
    minors: int = Field(ge=0, le=99)
    budget_min: Budget | None = None
    budget_max: Budget | None = None
    trip_types: TravelTypes = []
    accommodation_category: AccommodationCategory | None = None
    assigned_to_id: RecordId
    notes: Notes | None = None

    @field_validator("departure_date")
    @classmethod
    def departure_for_exact_dates(cls, value: date | None, info: ValidationInfo) -> date | None:
        _check_mode_field(
            value, info, used_with=DateMode.EXACT, required="Indica la fecha de salida."
        )
        return value

    @field_validator("return_date")
    @classmethod
    def return_after_departure(cls, value: date | None, info: ValidationInfo) -> date | None:
        if _check_mode_field(value, info, used_with=DateMode.EXACT):
            departure = info.data.get("departure_date")
            if departure is not None and value < departure:
                raise _error("before_departure", "No puede ser anterior a la salida.")
        return value

    @field_validator("window_start")
    @classmethod
    def window_start_for_flexible(cls, value: date | None, info: ValidationInfo) -> date | None:
        _check_mode_field(
            value, info, used_with=DateMode.FLEXIBLE, required="Indica desde cuándo."
        )
        return value

    @field_validator("window_end")
    @classmethod
    def window_end_after_start(cls, value: date | None, info: ValidationInfo) -> date | None:
        if _check_mode_field(
            value, info, used_with=DateMode.FLEXIBLE, required="Indica hasta cuándo."
        ):
            start = info.data.get("window_start")
            if start is not None and value < start:
                raise _error("before_start", "No puede ser anterior al inicio.")
        return value

    @field_validator("approx_nights")
    @classmethod
    def nights_fit_in_the_window(cls, value: int | None, info: ValidationInfo) -> int | None:
        if _check_mode_field(value, info, used_with=DateMode.FLEXIBLE):
            start, end = info.data.get("window_start"), info.data.get("window_end")
            if start is not None and end is not None and value > (end - start).days:
                raise _error("nights_do_not_fit", "No caben en el período elegido.")
        return value

    @field_validator("budget_max")
    @classmethod
    def maximum_not_below_minimum(cls, value: int | None, info: ValidationInfo) -> int | None:
        minimum = info.data.get("budget_min")
        if value is not None and minimum is not None and value < minimum:
            raise _error("below_minimum", "No puede ser menor que el mínimo.")
        return value


class TravelRequestCreate(TravelRequestInput):
    pass


class TravelRequestUpdate(TravelRequestInput):
    # El cliente viaja en el cuerpo para validarlo igual que al crear; el servicio revisa que
    # sea el mismo que ya tiene la solicitud.
    expected_version: int = Field(ge=1)


class TravelRequestClose(InputSchema):
    reason: CloseReason
    note: CloseNote | None = Field(default=None, validate_default=True)
    expected_version: int = Field(ge=1)

    @field_validator("note")
    @classmethod
    def other_needs_a_note(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("reason") == CloseReason.OTHER and value is None:
            raise _error("required", "Cuéntanos el motivo.")
        return value


class TravelRequestReopen(InputSchema):
    expected_version: int = Field(ge=1)


class StatusFilter(StrEnum):
    NEW = "new"
    QUOTING = "quoting"
    QUOTED = "quoted"
    CLOSED = "closed"
    # Las que todavía esperan una cotización: nuevas y en cotización.
    PENDING = "pending"


class RequestSort(StrEnum):
    # Lo último que se movió primero: la lista de trabajo del día.
    RECENT = "recent"
    # Lo que más lleva esperando primero: la lista de pendientes de cotización.
    OLDEST = "oldest"


class TravelRequestFilters(BaseModel):
    """Sin `extra="forbid"`: conviven con los parámetros de la paginación."""

    q: SearchText = ""
    status: StatusFilter | None = None
    assigned_to: RecordId | None = None
    client_id: RecordId | None = None
    sort: RequestSort = RequestSort.RECENT


class SummaryFilters(BaseModel):
    assigned_to: RecordId | None = None
    client_id: RecordId | None = None


class ClientRef(OutputSchema):
    id: int
    display_name: str


class AdvisorRef(UserRef):
    # La ficha marca al asesor responsable que ya no está activo.
    is_active: bool


class TravelRequestListItem(OutputSchema):
    id: int
    code: str
    client: ClientRef
    destination: str
    date_mode: DateMode
    departure_date: date | None
    return_date: date | None
    window_start: date | None
    window_end: date | None
    approx_nights: int | None
    adults: int
    minors: int
    status: TravelRequestStatus
    assigned_to: AdvisorRef
    created_at: datetime
    updated_at: datetime
    waiting_days: int


class TravelRequestDetail(TravelRequestListItem):
    origin: str | None
    budget_min: int | None
    budget_max: int | None
    trip_types: list[TravelType]
    accommodation_category: AccommodationCategory | None
    notes: str | None
    close_reason: CloseReason | None
    close_note: str | None
    closed_by: UserRef | None
    closed_at: datetime | None
    created_by: UserRef
    version: int


class StatusCounts(BaseModel):
    new: int
    quoting: int
    quoted: int
    closed: int


class TravelRequestSummary(BaseModel):
    by_status: StatusCounts
    total: int
    pending: int
    pending_over_3_days: int


class AdvisorOption(OutputSchema):
    id: int
    full_name: str
