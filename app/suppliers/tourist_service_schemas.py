from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    Field,
    SkipValidation,
    ValidationError,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.common.fields import optional_text, required_text, same_error
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.suppliers.service_attributes import ATTRIBUTE_MODELS, ServiceAttributes
from app.suppliers.service_types import ServiceType
from app.suppliers.tourist_service_models import TouristService

_SERVICE_TYPES = {member.value for member in ServiceType}

ServiceName = Annotated[str, AfterValidator(required_text(150))]
Destination = Annotated[str, AfterValidator(required_text(120))]
LongText = Annotated[str, AfterValidator(optional_text(2000))]


def _attribute_errors(data: Any) -> tuple[list[InitErrorDetails], Any]:
    """Valida `attributes` con el modelo de su tipo. Devuelve los errores, con su ruta dentro
    de `attributes`, o el modelo ya validado."""
    if not isinstance(data, dict) or data.get("service_type") not in _SERVICE_TYPES:
        # Sin un tipo válido no hay con qué validar: el error que se informa es el del tipo.
        return [], None
    raw = data.get("attributes", {})
    if not isinstance(raw, dict):
        error = PydanticCustomError(
            "invalid_attributes", "Los datos del tipo deben ser un objeto."
        )
        return [InitErrorDetails(type=error, loc=("attributes",), input=raw)], None
    model = ATTRIBUTE_MODELS[ServiceType(data["service_type"])]
    try:
        return [], model.model_validate(raw)
    except ValidationError as error:
        return [
            same_error(detail | {"loc": ("attributes", *detail["loc"])})
            for detail in error.errors()
        ], None


class TouristServiceInput(InputSchema):
    service_type: ServiceType
    name: ServiceName
    destination: Destination
    description: LongText | None = None
    conditions: LongText | None = None
    # La unión queda en el esquema OpenAPI, pero no valida: qué modelo corresponde lo dice
    # `service_type`, no la forma del objeto. La validación real está en el validador de abajo.
    attributes: Annotated[ServiceAttributes, SkipValidation] = Field(default_factory=dict)

    @model_validator(mode="wrap")
    @classmethod
    def attributes_of_its_type(cls, data: Any, handler):
        # Una unión discriminada de todo el cuerpo pondría el tipo en la ruta de cada error
        # ("lodging.attributes.max_capacity") y el formulario no sabría dónde mostrarlo. Aquí
        # los errores de los atributos salen con su ruta y junto con los demás del cuerpo.
        attribute_errors, attributes = _attribute_errors(data)
        try:
            service = handler(data)
        except ValidationError as error:
            if not attribute_errors:
                raise
            raise ValidationError.from_exception_data(
                cls.__name__, [*map(same_error, error.errors()), *attribute_errors]
            ) from None
        if attribute_errors:
            raise ValidationError.from_exception_data(cls.__name__, attribute_errors)
        if attributes is not None:
            service.attributes = attributes
        return service


class TouristServiceCreate(TouristServiceInput):
    pass


class TouristServiceUpdate(TouristServiceInput):
    expected_version: int = Field(ge=1)


class TouristServiceStatusChange(InputSchema):
    expected_version: int = Field(ge=1)


class SupplierRef(OutputSchema):
    id: int
    trade_name: str
    is_active: bool


class TouristServiceListItem(OutputSchema):
    id: int
    service_type: ServiceType
    name: str
    destination: str
    is_active: bool
    current_rate_count: int

    @classmethod
    def from_service(cls, service: TouristService, current_rate_count: int):
        """El conteo no es una columna: lo calcula la consulta junto con el servicio."""
        values = {
            field: getattr(service, field)
            for field in cls.model_fields
            if field not in {"current_rate_count", "attributes"}
        }
        if "attributes" in cls.model_fields:
            model = ATTRIBUTE_MODELS[ServiceType(service.service_type)]
            values["attributes"] = model.model_validate(service.attributes)
        return cls.model_validate(values | {"current_rate_count": current_rate_count})


class TouristServiceDetail(TouristServiceListItem):
    supplier: SupplierRef
    description: str | None
    conditions: str | None
    # Se arma con el modelo de su tipo (`from_service`), no adivinando por la forma del objeto.
    attributes: ServiceAttributes
    deactivated_at: datetime | None
    deactivated_by: UserRef | None
    created_by: UserRef
    created_at: datetime
    updated_at: datetime
    version: int
