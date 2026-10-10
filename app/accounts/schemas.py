from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.accounts.models import DocumentType


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    document_number: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
    ]
    # Sin recortar, y con tope: un cuerpo enorme obligaría a calcular Argon2 sobre megas.
    password: str = Field(min_length=1, max_length=256)


class RoleSummary(BaseModel):
    id: int
    name: str


class SessionUser(BaseModel):
    id: int
    email: str
    full_name: str
    role: RoleSummary
    permissions: list[str]
