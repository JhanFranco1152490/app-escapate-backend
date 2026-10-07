from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Devuelve si coincide y, si los parámetros del hash cambiaron, el hash nuevo a guardar."""
    return _hasher.verify_and_update(password, password_hash)
