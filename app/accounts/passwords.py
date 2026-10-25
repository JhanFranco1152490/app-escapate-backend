from app.common.identifiers import normalize_document, normalize_email

MIN_LENGTH = 12
MAX_LENGTH = 256


def password_problems(password: str, *, email: str, document_number: str) -> list[str]:
    """Reglas para fijar una contraseña. Lista vacía si se puede usar.

    Sin reglas de composición (mayúscula, número, símbolo): empujan a contraseñas
    predecibles, y la longitud protege más.
    """
    if len(password) < MIN_LENGTH:
        return [f"La contraseña debe tener al menos {MIN_LENGTH} caracteres."]
    if len(password) > MAX_LENGTH:
        return [f"La contraseña no puede tener más de {MAX_LENGTH} caracteres."]
    if normalize_email(password) == normalize_email(email) or (
        normalize_document(password) == document_number
    ):
        return ["La contraseña no puede ser tu correo ni tu documento."]
    return []
