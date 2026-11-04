"""Creación de una cuenta con un rol dado desde la terminal, sin invitación por correo: la usan
`create-admin` y la carga de cuentas de demostración."""

from pydantic import ValidationError
from sqlmodel import Session, select

from app.accounts.models import Role, UserAccount
from app.accounts.passwords import password_problems
from app.accounts.schemas import UserInput
from app.core.security.passwords import hash_password

_LABELS = {
    "first_name": "Nombres",
    "last_name": "Apellidos",
    "email": "Correo",
    "document_type": "Tipo de documento",
    "document_number": "Número de documento",
    "phone": "Celular",
}


class SetupError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


def missing_role(name: str) -> SetupError:
    return SetupError([f"No existe el rol {name}. ¿Se aplicaron las migraciones?"])


def _validation_messages(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors():
        field = item["loc"][-1]
        # El tipo de documento es un enum de la API: su mensaje por defecto no está en español.
        text = "Debe ser CC, CE, PPT o PA." if field == "document_type" else item["msg"]
        messages.append(f"{_LABELS[field]}: {text}")
    return messages


def create_account(
    session: Session,
    role: Role,
    *,
    first_name: str,
    last_name: str,
    email: str,
    document_type: str,
    document_number: str,
    phone: str,
    password: str,
) -> UserAccount:
    try:
        data = UserInput(
            first_name=first_name,
            last_name=last_name,
            email=email,
            document_type=document_type.strip().upper(),
            document_number=document_number,
            phone=phone,
        )
    except ValidationError as error:
        raise SetupError(_validation_messages(error)) from None

    # La contraseña se compara con el correo y el documento ya normalizados, así que se
    # revisa después de validar los demás datos.
    problems = password_problems(password, email=data.email, document_number=data.document_number)
    if problems:
        raise SetupError(problems)

    if session.exec(select(UserAccount.id).where(UserAccount.email == data.email)).first():
        raise SetupError(["Ya existe una cuenta con ese correo."])
    duplicate_document = select(UserAccount.id).where(
        UserAccount.document_type == data.document_type,
        UserAccount.document_number == data.document_number,
    )
    if session.exec(duplicate_document).first():
        raise SetupError(["Ya existe una cuenta con ese documento."])
    if session.exec(select(UserAccount.id).where(UserAccount.phone == data.phone)).first():
        raise SetupError(["Ya existe una cuenta con ese celular."])

    user = UserAccount(
        **data.model_dump(mode="json"),
        password_hash=hash_password(password),
        role_id=role.id,
    )
    session.add(user)
    session.commit()
    return user
