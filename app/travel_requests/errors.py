from app.common.errors import ApiError, FieldError

UNKNOWN_CLIENT = "El cliente no existe."
INELIGIBLE_ADVISOR = "Elige un asesor activo que pueda gestionar solicitudes."
DATE_IN_PAST = "La fecha ya pasó."


class TravelRequestClosed(ApiError):
    status_code, code = 409, "travel_request_closed"
    detail = "La solicitud está cerrada. Reábrela para modificarla."


class TravelRequestNotClosed(ApiError):
    status_code, code = 409, "travel_request_not_closed"
    detail = "La solicitud no está cerrada."


class ClientChanged(FieldError):
    field, message = "client_id", "El cliente de la solicitud no se puede cambiar."
