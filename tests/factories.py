import factory

from app.accounts.models import Role, UserAccount
from app.core.security.passwords import hash_password

PASSWORD = "contrasena-de-prueba-123"
# Argon2 es lento a propósito: un solo hash para todas las cuentas de prueba.
PASSWORD_HASH = hash_password(PASSWORD)

_current = {"session": None}


def use_session(session) -> None:
    """Las fábricas escriben en la sesión de la prueba en curso (con rollback al final)."""
    _current["session"] = session


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_factory = lambda: _current["session"]  # noqa: E731
        sqlalchemy_session_persistence = "flush"


class RoleFactory(BaseFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"Rol de prueba {n}")


class UserAccountFactory(BaseFactory):
    class Meta:
        model = UserAccount

    email = factory.Sequence(lambda n: f"persona{n}@example.com")
    first_name = "Persona"
    last_name = factory.Sequence(lambda n: f"Apellido {n}")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: str(10_000_000 + n))
    phone = factory.Sequence(lambda n: f"300{n:07d}")
    password_hash = PASSWORD_HASH
    is_active = True
    role = factory.SubFactory(RoleFactory)
