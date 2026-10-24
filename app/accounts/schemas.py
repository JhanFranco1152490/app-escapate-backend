import unicodedata
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.accounts.identifiers import (
    is_valid_document,
    is_valid_phone,
    normalize_document,
    normalize_email,
    normalize_phone,
)
from app.accounts.models import DocumentType, LoginMethod
from app.accounts.services.reset_tokens import TokenPurpose

# Sin recortar, y con tope: un cuerpo enorme obligaría a calcular Argon2 sobre megas.
Password = Annotated[str, Field(min_length=1, max_length=256)]

# Cabe en BIGINT: un id mayor haría fallar la consulta en la base en vez de no encontrar nada.
RecordId = Annotated[int, Field(ge=1, le=2**63 - 1)]

NAME_MAX_LENGTH = 75
ROLE_NAME_MAX_LENGTH = 80
ROLE_DESCRIPTION_MAX_LENGTH = 200
PERMISSIONS_MAX_COUNT = 100
PERMISSION_CODE_MAX_LENGTH = 100
EMAIL_MAX_LENGTH = 254
DOCUMENT_MAX_LENGTH = 30
PHONE_MAX_LENGTH = 20


_FORBIDDEN_CATEGORIES = {"Cc", "Cf"}


def _without_control_characters(text: str) -> str:
    """Un texto escrito por una persona no lleva caracteres de control (categoría Cc) ni de
    formato invisibles (Cf: ancho cero, cambio de dirección del texto), que permiten que dos
    nombres idénticos a la vista no lo sean. El NUL (0x00) ni siquiera se puede guardar en
    PostgreSQL: llegaría a la base y fallaría con un 500."""
    if any(unicodedata.category(character) in _FORBIDDEN_CATEGORIES for character in text):
        raise PydanticCustomError("invalid_characters", "Contiene caracteres que no se permiten.")
    return text


def _trimmed_text(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) > max_length:
        raise PydanticCustomError("too_long", f"Máximo {max_length} caracteres.")
    return _without_control_characters(text)


def _required_text(max_length: int) -> Callable[[str], str]:
    def validate(value: str) -> str:
        text = _trimmed_text(value, max_length)
        if not text:
            raise PydanticCustomError("required", "Este campo es obligatorio.")
        return text

    return validate


def _optional_text(max_length: int) -> Callable[[str], str | None]:
    def validate(value: str) -> str | None:
        return _trimmed_text(value, max_length) or None

    return validate


def _email(value: str) -> str:
    candidate = normalize_email(value)
    invalid = PydanticCustomError("invalid_email", "No es un correo válido.")
    if len(candidate) > EMAIL_MAX_LENGTH:
        raise invalid
    try:
        # Solo ASCII: los Gmail lo son, y así dos escrituras unicode del mismo correo no
        # se guardan como cuentas distintas.
        return validate_email(
            candidate, check_deliverability=False, allow_smtputf8=False
        ).normalized
    except EmailNotValidError:
        raise invalid from None


def _phone(value: str) -> str:
    number = normalize_phone(value) if len(value) <= PHONE_MAX_LENGTH else ""
    if not is_valid_phone(number):
        raise PydanticCustomError("invalid_phone", "Debe ser un celular colombiano de 10 dígitos.")
    return number


# Cada tipo normaliza y valida en el mismo paso: lo que se guarda es exactamente lo que se
# validó.
PersonName = Annotated[str, AfterValidator(_required_text(NAME_MAX_LENGTH))]
Email = Annotated[str, AfterValidator(_email)]
Phone = Annotated[str, AfterValidator(_phone)]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentInput(_Input):
    document_type: DocumentType
    document_number: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
    ]


class LoginRequest(DocumentInput):
    password: Password


class PasswordResetRequest(DocumentInput):
    pass


class UserInput(_Input):
    first_name: PersonName
    last_name: PersonName
    email: Email
    document_type: DocumentType
    document_number: str
    phone: Phone

    @field_validator("document_number")
    @classmethod
    def normalize_and_check_document(cls, value: str, info: ValidationInfo) -> str:
        number = normalize_document(value) if len(value) <= DOCUMENT_MAX_LENGTH else ""
        # Si el tipo ya falló, ese error es el que se informa; aquí solo se normaliza.
        document_type = info.data.get("document_type")
        if document_type is None:
            return number
        if not is_valid_document(document_type, number):
            raise PydanticCustomError("invalid_document", "No es válido para ese tipo.")
        return number


class UserCreate(UserInput):
    role_id: RecordId


class UserRoleInput(_Input):
    role_id: RecordId


RoleName = Annotated[str, AfterValidator(_required_text(ROLE_NAME_MAX_LENGTH))]
# Vacía o de solo espacios se guarda como None.
RoleDescription = Annotated[str, AfterValidator(_optional_text(ROLE_DESCRIPTION_MAX_LENGTH))]
PermissionCode = Annotated[str, Field(max_length=PERMISSION_CODE_MAX_LENGTH)]


class RoleInput(_Input):
    name: RoleName
    description: RoleDescription | None = None
    # Solo la forma: que cada código exista y traiga sus dependencias lo revisa el servicio,
    # que necesita el registro y sus descripciones para el mensaje.
    permissions: list[PermissionCode] = Field(max_length=PERMISSIONS_MAX_COUNT)


class PasswordResetAccepted(BaseModel):
    detail: str


class ResetTokenCheck(_Input):
    token: str = Field(min_length=1, max_length=500)


class ResetTokenInfo(BaseModel):
    purpose: TokenPurpose
    full_name: str


class PasswordResetConfirm(ResetTokenCheck):
    password: Password
    password_confirmation: Password


class _Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RoleSummary(_Output):
    id: int
    name: str


class RoleListItem(RoleSummary):
    description: str | None
    is_protected: bool
    # Cuentas con el rol, activas e inactivas: es lo que impide borrarlo.
    user_count: int
    inactive_user_count: int


class RoleDetail(RoleListItem):
    # Códigos del registro, en orden alfabético.
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class PermissionItem(BaseModel):
    code: str
    section: str
    group: str
    label: str
    description: str
    requires: list[str]
    help: str | None


class SessionUser(BaseModel):
    id: int
    email: str
    full_name: str
    role: RoleSummary
    permissions: list[str]


class UserFilters(BaseModel):
    q: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=100),
        AfterValidator(_without_control_characters),
    ] = ""
    status: Literal["active", "inactive"] | None = None
    role_id: RecordId | None = None


class UserListItem(_Output):
    id: int
    first_name: str
    last_name: str
    full_name: str
    email: str
    role: RoleSummary
    is_active: bool
    invitation_pending: bool
    last_activity_at: datetime | None


class UserDetail(UserListItem):
    document_type: DocumentType
    document_number: str
    phone: str | None
    has_password: bool
    google_linked: bool
    created_at: datetime
    updated_at: datetime


class LoginEventItem(_Output):
    created_at: datetime
    method: LoginMethod


class UserSaved(BaseModel):
    user: UserDetail
    # None si no hizo falta enviar la invitación; False si se intentó y el correo falló.
    invitation_sent: bool | None
