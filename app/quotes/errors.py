from app.common.errors import ApiError

UNKNOWN_REQUEST = "La solicitud no existe."
UNKNOWN_SERVICE = "El servicio no existe."
INACTIVE_SERVICE = "El servicio está inactivo."
SERVICE_TYPE_MISMATCH = "No coincide con el tipo del servicio elegido."
UNKNOWN_SUPPLIER = "El proveedor no existe."
SUPPLIER_OF_THE_SERVICE = "El proveedor sale del servicio elegido."
CHARGE_UNIT_MISMATCH = "No es una unidad de cobro de este tipo de servicio."
VALIDITY_IN_PAST = "La vigencia ya pasó."
BAD_ALTERNATIVE = "Elige un servicio incluido de esta misma cotización."


class QuoteNotEditable(ApiError):
    status_code, code = 409, "quote_not_editable"
    detail = "Solo se edita una cotización en borrador. Devuélvela a borrador para cambiarla."


class NotAnAlternative(ApiError):
    status_code, code = 409, "not_an_alternative"
    detail = "Ese servicio no es una alternativa de otro: ya está incluido."


class QuoteWrongStatus(ApiError):
    status_code, code = 409, "quote_wrong_status"
    detail = "La cotización no está en el estado que permite esta acción."


class QuoteWithoutItems(ApiError):
    status_code, code = 409, "quote_without_items"
    detail = "Agrega al menos un servicio antes de enviar la cotización."


class QuoteWithoutExchangeRate(ApiError):
    status_code, code = 409, "exchange_rate_missing"
    detail = (
        "Hay servicios en dólares y la cotización no tiene tasa de cambio. "
        "Agrégala en los precios antes de enviarla."
    )


class QuoteExpired(ApiError):
    status_code, code = 409, "quote_expired"
    detail = "La cotización venció. Devuélvela a borrador y actualiza la vigencia."
