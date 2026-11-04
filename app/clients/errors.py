from app.common.errors import FieldError, InvalidFields


class DuplicateClient(FieldError):
    field, message = "document_number", "Ya existe un cliente con ese documento."


class DuplicateTraveler(FieldError):
    field, message = "document_number", "Ya existe un viajero con ese documento."


class ClientTypeChanged(FieldError):
    field, message = "client_type", "El tipo de cliente no se puede cambiar."


class ClientAlreadyTraveler(FieldError):
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
