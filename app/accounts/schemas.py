from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.accounts.models import DocumentType
from app.accounts.services.reset_tokens import TokenPurpose

# Sin recortar, y con tope: un cuerpo enorme obligaría a calcular Argon2 sobre megas.
Password = Annotated[str, Field(min_length=1, max_length=256)]


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


class RoleSummary(BaseModel):
    id: int
    name: str


class SessionUser(BaseModel):
    id: int
    email: str
    full_name: str
    role: RoleSummary
    permissions: list[str]
