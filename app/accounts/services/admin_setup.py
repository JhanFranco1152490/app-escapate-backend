"""Creación de un administrador desde la terminal: la primera cuenta, o un respaldo si el único
administrador pierde el acceso."""

from sqlmodel import Session, select

from app.accounts.identifiers import is_valid_document, normalize_document, normalize_email
from app.accounts.models import DocumentType, Role, UserAccount
from app.accounts.passwords import password_problems
from app.core.security.passwords import hash_password

ADMIN_ROLE = "Administrador"


class SetupError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


def _problems(full_name: str, email: str, document_type: str, number: str, password: str):
    problems = []
    if not full_name.strip() or len(full_name.strip()) > 150:
        problems.append("Escribe el nombre (máximo 150 caracteres).")
    if "@" not in email or len(email) > 254:
        problems.append("El correo no es válido.")
    if document_type not in DocumentType.__members__.values():
        problems.append("El tipo de documento debe ser CC, CE, PPT o PA.")
    elif not is_valid_document(document_type, number):
        problems.append("El número de documento no es válido para ese tipo.")
    return problems + password_problems(password, email=email, document_number=number)


def create_admin(
    session: Session,
    *,
    full_name: str,
    email: str,
    document_type: str,
    document_number: str,
    password: str,
) -> UserAccount:
    email, number = normalize_email(email), normalize_document(document_number)
    document_type = document_type.strip().upper()
    problems = _problems(full_name, email, document_type, number, password)
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

    user = UserAccount(
        full_name=full_name.strip(),
        email=email,
        document_type=document_type,
        document_number=number,
        password_hash=hash_password(password),
        role_id=role.id,
    )
    session.add(user)
    session.commit()
    return user
