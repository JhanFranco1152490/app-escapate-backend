"""Los campos propios de cada tipo de servicio. Se guardan en la columna `attributes` y solo
estos modelos deciden su forma: la base apenas comprueba que sea un objeto."""

from datetime import time
from typing import Annotated, Any

from pydantic import AfterValidator, Field, PlainSerializer
from pydantic_core import PydanticCustomError

from app.common.fields import fixed_choices, optional_text, required_text
from app.common.schemas import InputSchema
from app.suppliers.service_types import (
    CabinClass,
    CabinKind,
    CruiseInclude,
    DurationUnit,
    LodgingInclude,
    LodgingKind,
    Meal,
    MealPlan,
    Modality,
    ServiceStyle,
    ServiceType,
    ToursInclude,
    TripType,
    VehicleKind,
    WholesalerInclude,
)

_UNKNOWN_OPTION = "No es una opción válida."
_REPEATED_OPTION = "Hay una opción repetida."


def _includes(choices) -> Any:
    return fixed_choices(choices, unknown=_UNKNOWN_OPTION, repeated=_REPEATED_OPTION)


def _whole_minutes(value: time) -> time:
    # Una hora de llegada o salida se pacta en horas y minutos, sin zona: la del hotel.
    if value.second or value.microsecond or value.tzinfo is not None:
        raise PydanticCustomError("invalid_time", "Indica la hora en horas y minutos.")
    return value


Place = Annotated[str, AfterValidator(required_text(120))]
OptionalPlace = Annotated[str, AfterValidator(optional_text(120))]
ClockTime = Annotated[
    time,
    AfterValidator(_whole_minutes),
    PlainSerializer(lambda value: value.strftime("%H:%M"), return_type=str, when_used="json"),
]


class LodgingAttributes(InputSchema):
    lodging_kind: LodgingKind
    stars: int | None = Field(default=None, ge=1, le=5)
    meal_plan: MealPlan | None = None
    max_capacity: int = Field(ge=1, le=50)
    check_in_time: ClockTime | None = None
    check_out_time: ClockTime | None = None
    includes: _includes(LodgingInclude) = []


class AirAttributes(InputSchema):
    origin: Place
    trip_type: TripType
    cabin_class: CabinClass | None = None
    stops: int | None = Field(default=None, ge=0, le=3)
    carry_on_included: bool = False
    checked_bags: int | None = Field(default=None, ge=0, le=5)


class GroundAttributes(InputSchema):
    modality: Modality
    vehicle_kind: VehicleKind | None = None
    origin: OptionalPlace | None = None
    max_capacity: int | None = Field(default=None, ge=1, le=60)


class ToursAttributes(InputSchema):
    duration_value: int = Field(ge=1, le=999)
    duration_unit: DurationUnit
    modality: Modality | None = None
    meeting_point: Annotated[str, AfterValidator(optional_text(200))] | None = None
    includes: _includes(ToursInclude) = []


class CruiseAttributes(InputSchema):
    ship_name: Place
    departure_port: Place
    nights: int = Field(ge=1, le=60)
    cabin_kind: CabinKind | None = None
    itinerary: Annotated[str, AfterValidator(optional_text(500))] | None = None
    includes: _includes(CruiseInclude) = []


class FoodAttributes(InputSchema):
    meals: fixed_choices(
        Meal,
        unknown=_UNKNOWN_OPTION,
        repeated=_REPEATED_OPTION,
        required="Elige al menos una comida.",
    )
    service_style: ServiceStyle | None = None
    cuisine: Annotated[str, AfterValidator(optional_text(80))] | None = None


class WholesalerAttributes(InputSchema):
    # 0 noches es un pasadía.
    nights: int = Field(ge=0, le=60)
    departure_city: OptionalPlace | None = None
    includes: _includes(WholesalerInclude) = []


class OtherAttributes(InputSchema):
    """Sin campos propios: el servicio se describe en su descripción."""


ATTRIBUTE_MODELS: dict[ServiceType, type[InputSchema]] = {
    ServiceType.LODGING: LodgingAttributes,
    ServiceType.AIR: AirAttributes,
    ServiceType.GROUND: GroundAttributes,
    ServiceType.TOURS: ToursAttributes,
    ServiceType.CRUISE: CruiseAttributes,
    ServiceType.FOOD: FoodAttributes,
    ServiceType.WHOLESALER: WholesalerAttributes,
    ServiceType.OTHER: OtherAttributes,
}

# Para la salida y el esquema OpenAPI. La entrada no se valida con esta unión: cuál modelo
# corresponde lo dice el tipo del servicio, no la forma del objeto.
ServiceAttributes = (
    LodgingAttributes
    | AirAttributes
    | GroundAttributes
    | ToursAttributes
    | CruiseAttributes
    | FoodAttributes
    | WholesalerAttributes
    | OtherAttributes
)


def stored_attributes(attributes: InputSchema) -> dict[str, Any]:
    """Lo que se guarda en la columna: ya validado y sin los opcionales que no se llenaron,
    así que lo que se lea de la base siempre cumple el modelo de su tipo."""
    return attributes.model_dump(mode="json", exclude_none=True)
