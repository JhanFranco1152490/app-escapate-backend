from app.common.errors import InvalidFields


class _FieldError(InvalidFields):
    """Un solo campo con un mensaje fijo."""

    field: str
    message: str

    def __init__(self):
        super().__init__(fields={self.field: [self.message]})


class DuplicateClient(_FieldError):
    field, message = "document_number", "Ya existe un cliente con ese documento."


class DuplicateTraveler(_FieldError):
    field, message = "document_number", "Ya existe un viajero con ese documento."


class ClientTypeChanged(_FieldError):
    field, message = "client_type", "El tipo de cliente no se puede cambiar."


class ClientAlreadyTraveler(_FieldError):
    field, message = "is_the_client", "Este cliente ya tiene su ficha de viajero."


class InvalidReferenceClient(InvalidFields):
    """El cliente de referencia de un viajero no sirve."""

    @classmethod
    def missing(cls) -> "InvalidReferenceClient":
        return cls(fields={"reference_client_id": ["Elige un cliente registrado."]})

    @classmethod
    def company(cls) -> "InvalidReferenceClient":
        # Solo con "es el mismo cliente": una empresa no viaja, viajan sus empleados.
        return cls(fields={"reference_client_id": ["Solo una persona puede ser también viajero."]})
