MAX_PATH_LENGTH = 2000


def safe_next_path(value: str) -> str:
    """Ruta interna a la que volver después de entrar; cualquier otra cosa vuelve al inicio.

    Evita usar el login para mandar a alguien a otro sitio: "//sitio" y "/\\sitio" los
    navegadores los interpretan como direcciones de otro dominio.
    """
    is_internal = (
        value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
        and len(value) <= MAX_PATH_LENGTH
        and all(32 <= ord(char) != 127 for char in value)
    )
    return value if is_internal else "/"
