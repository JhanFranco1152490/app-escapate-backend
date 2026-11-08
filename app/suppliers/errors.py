from app.common.errors import ApiError, FieldError, InvalidFields
from app.suppliers.service_types import SERVICE_TYPE_LABELS, ServiceType


class DuplicateSupplier(FieldError):
    field, message = "document_number", "Ya existe un proveedor con ese documento."


class SupplierInactive(ApiError):
    status_code, code = 409, "supplier_inactive"
    detail = (
        "El proveedor está inactivo. Actívalo antes de registrarle servicios o activar uno de "
        "ellos."
    )


class ServiceInactive(ApiError):
    status_code, code = 409, "service_inactive"
    detail = "El servicio está inactivo. Actívalo antes de agregarle tarifas."


class ServiceTypeNotOffered(InvalidFields):
    def __init__(self, service_type: str):
        label = SERVICE_TYPE_LABELS[ServiceType(service_type)]
        super().__init__(
            fields={
                "service_type": [
                    f"El proveedor no tiene la clasificación {label}. Agrégala en su ficha "
                    "antes de registrar este servicio."
                ]
            }
        )


class ServiceTypeChanged(FieldError):
    field, message = "service_type", "El tipo de un servicio no se puede cambiar."


class ChargeUnitNotAllowed(FieldError):
    field, message = "charge_unit", "Esa unidad no aplica a este tipo de servicio."
