"""Creación de un administrador desde la terminal: la primera cuenta, o un respaldo si el único
administrador pierde el acceso."""

from sqlmodel import Session, select

from app.accounts.identifiers import (
    is_valid_document,
    is_valid_phone,
    normalize_document,
    normalize_email,
    normalize_phone,
)
from app.accounts.models import DocumentType, Role, UserAccount
from app.accounts.passwords import password_problems
from app.core.security.passwords import hash_password

ADMIN_ROLE = "Administrador"


class SetupError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


def _problems(
    first_name: str, last_name: str, email: str, document_type: str, number: str, phone: str
):
    problems = []
    if not first_name.strip() or len(first_name.strip()) > 75:
        problems.append("Escribe los nombres (máximo 75 caracteres).")
    if not last_name.strip() or len(last_name.strip()) > 75:
        problems.append("Escribe los apellidos (máximo 75 caracteres).")
    if "@" not in email or len(email) > 254:
        problems.append("El correo no es válido.")
    if document_type not in DocumentType.__members__.values():
        problems.append("El tipo de documento debe ser CC, CE, PPT o PA.")
    elif not is_valid_document(document_type, number):
        problems.append("El número de documento no es válido para ese tipo.")
    if not is_valid_phone(phone):
        problems.append("El celular debe ser colombiano, de 10 dígitos.")
    return problems


def create_admin(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    email: str,
    document_type: str,
    document_number: str,
    phone: str,
    password: str,
) -> UserAccount:
    email = normalize_email(email)
    number = normalize_document(document_number)
    document_type = document_type.strip().upper()
    phone = normalize_phone(phone)
    problems = _problems(first_name, last_name, email, document_type, number, phone)
    problems += password_problems(password, email=email, document_number=number)
    if problems:
        raise SetupError(problems)

    role = session.exec(select(Role).where(Role.name == ADMIN_ROLE)).first()
    if role is None:
        raise SetupError([f"No existe el rol {ADMIN_ROLE}. ¿Se aplicaron las migraciones?"])
    if session.exec(select(UserAccount.id).where(UserAccount.email == email)).first():
        raise SetupError(["Ya existe una cuenta con ese correo."])
    duplicate_document = select(UserAccount.id).where(
        UserAccount.document_type == document_type, UserAccount.document_number == number
    )
    if session.exec(duplicate_document).first():
        raise SetupError(["Ya existe una cuenta con ese documento."])
    if session.exec(select(UserAccount.id).where(UserAccount.phone == phone)).first():
        raise SetupError(["Ya existe una cuenta con ese celular."])

    user = UserAccount(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email,
        document_type=document_type,
        document_number=number,
        phone=phone,
        password_hash=hash_password(password),
        role_id=role.id,
    )
    session.add(user)
    session.commit()
    return user
