import phonenumbers

PHONE_MAX_LENGTH = 25
# Sin indicativo, el número se lee como colombiano: es el caso de casi todos los clientes.
DEFAULT_REGION = "CO"


def normalize_international_phone(value: str) -> str | None:
    """El teléfono en formato E.164 (`+573001112233`), o `None` si no es válido para su país.

    Se guarda así para que un mismo número escrito de distintas formas ("300 111 2233",
    "+57 300 111 2233") sea siempre el mismo valor al buscarlo o compararlo.
    """
    if len(value) > PHONE_MAX_LENGTH:
        return None
    try:
        number = phonenumbers.parse(value, DEFAULT_REGION)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
