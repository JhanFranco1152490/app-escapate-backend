from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.accounts.identifiers import is_valid_phone, normalize_phone
from app.accounts.models import DocumentType, LoginMethod
from app.accounts.services.reset_tokens import TokenPurpose
from app.common.fields import (
    Email,
    PersonName,
    RecordId,
    optional_text,
    required_text,
    without_control_characters,
)
from app.common.identifiers import is_valid_document, normalize_document
from app.common.schemas import InputSchema as _Input
from app.common.schemas import OutputSchema as _Output

# Sin recortar, y con tope: un cuerpo enorme obligaría a calcular Argon2 sobre megas.
Password = Annotated[str, Field(min_length=1, max_length=256)]

ROLE_NAME_MAX_LENGTH = 80
ROLE_DESCRIPTION_MAX_LENGTH = 200
PERMISSIONS_MAX_COUNT = 100
PERMISSION_CODE_MAX_LENGTH = 100
DOCUMENT_MAX_LENGTH = 30
PHONE_MAX_LENGTH = 20


def _phone(value: str) -> str:
    number = normalize_phone(value) if len(value) <= PHONE_MAX_LENGTH else ""
    if not is_valid_phone(number):
        raise PydanticCustomError("invalid_phone", "Debe ser un celular colombiano de 10 dígitos.")
    return number


# Normaliza y valida en el mismo paso, como los tipos de app.common.fields.
Phone = Annotated[str, AfterValidator(_phone)]


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


RoleName = Annotated[str, AfterValidator(required_text(ROLE_NAME_MAX_LENGTH))]
# Vacía o de solo espacios se guarda como None.
RoleDescription = Annotated[str, AfterValidator(optional_text(ROLE_DESCRIPTION_MAX_LENGTH))]
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
        AfterValidator(without_control_characters),
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
