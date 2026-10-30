from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlmodel import Field, Relationship, SQLModel

from app.common.columns import foreign_key, in_values, primary_key, timestamp


class DocumentType(StrEnum):
    CC = "CC"
    CE = "CE"
    PPT = "PPT"
    PA = "PA"


class LoginMethod(StrEnum):
    DOCUMENT = "document"
    GOOGLE = "google"
    EMAIL_LINK = "email_link"


class RevokeReason(StrEnum):
    ROTATED = "rotated"
    LOGOUT = "logout"
    REUSE_DETECTED = "reuse_detected"
    SESSION_LIMIT = "session_limit"
    ACCOUNT_DISABLED = "account_disabled"
    PASSWORD_CHANGED = "password_changed"
    GOOGLE_UNLINKED = "google_unlinked"


class Role(SQLModel, table=True):
    __tablename__ = "role"
    __table_args__ = (
        # "Operativo" y "operativo" son el mismo rol.
        Index("uq_role_name_lower", func.lower(text("name")), unique=True),
    )

    id: int | None = primary_key()
    name: str = Field(max_length=80)
    description: str | None = Field(default=None, max_length=200)
    # El rol Administrador: no se renombra, no se borra y siempre tiene todos los permisos.
    is_protected: bool = Field(default=False, sa_column_kwargs={"server_default": false()})
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permission"

    role_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)
    )
    permission: str = Field(max_length=100, primary_key=True)


class UserAccount(SQLModel, table=True):
    __tablename__ = "user_account"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number", name="uq_user_account_document"),
        UniqueConstraint("phone", name="uq_user_account_phone"),
        CheckConstraint(
            in_values("document_type", DocumentType), name="ck_user_account_document_type"
        ),
    )

    id: int | None = primary_key()
    email: str = Field(max_length=254, unique=True)
    first_name: str = Field(max_length=75)
    last_name: str = Field(max_length=75)
    document_type: str = Field(max_length=3)
    document_number: str = Field(max_length=20)
    phone: str | None = Field(default=None, max_length=10)
    password_hash: str | None = Field(default=None, max_length=255)
    google_sub: str | None = Field(default=None, max_length=255, unique=True)
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": true()})
    role_id: int = foreign_key("role.id", ondelete="RESTRICT")
    last_activity_at: datetime | None = timestamp(nullable=True)
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())

    role: Role = Relationship()

    @property
    def full_name(self) -> str:
        if not self.last_name:
            return self.first_name
        return f"{self.first_name} {self.last_name}"

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def google_linked(self) -> bool:
        return self.google_sub is not None

    @property
    def invitation_pending(self) -> bool:
        """Todavía no ha entrado por ninguna vía: no creó contraseña ni vinculó Google."""
        return not self.has_password and not self.google_linked


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_token"

    id: int | None = primary_key()
    jti: str = Field(max_length=64, unique=True)
    user_id: int = foreign_key("user_account.id", ondelete="CASCADE", index=True)
    issued_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = timestamp(nullable=True)
    revoke_reason: str | None = Field(default=None, max_length=20)


class LoginAttempt(SQLModel, table=True):
    __tablename__ = "login_attempt"
    __table_args__ = (UniqueConstraint("identifier", "ip", name="uq_login_attempt_pair"),)

    id: int | None = primary_key()
    identifier: str = Field(sa_column=Column(String(64), nullable=False))
    ip: str = Field(max_length=45)
    failures: int = Field(default=0)
    locked_until: datetime | None = timestamp(nullable=True)
    updated_at: datetime | None = timestamp(onupdate=func.now())


class LoginEvent(SQLModel, table=True):
    __tablename__ = "login_event"
    __table_args__ = (
        CheckConstraint(in_values("method", LoginMethod), name="ck_login_event_method"),
        Index("ix_login_event_user_created", "user_id", "created_at"),
        Index("ix_login_event_created_at", "created_at"),
    )

    id: int | None = primary_key()
    user_id: int = foreign_key("user_account.id", ondelete="CASCADE")
    method: str = Field(max_length=10)
    ip: str = Field(max_length=45)
    created_at: datetime | None = timestamp()
