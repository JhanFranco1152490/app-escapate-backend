from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlmodel import Field, Relationship, SQLModel


class DocumentType(StrEnum):
    CC = "CC"
    CE = "CE"
    PPT = "PPT"
    PA = "PA"


class LoginMethod(StrEnum):
    DOCUMENT = "document"
    GOOGLE = "google"


class RevokeReason(StrEnum):
    ROTATED = "rotated"
    LOGOUT = "logout"
    REUSE_DETECTED = "reuse_detected"
    SESSION_LIMIT = "session_limit"
    ACCOUNT_DISABLED = "account_disabled"


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def _primary_key():
    return Field(default=None, sa_column=Column(BigInteger, Identity(), primary_key=True))


def _foreign_key(target: str, ondelete: str, **kwargs):
    return Field(
        sa_column=Column(
            BigInteger, ForeignKey(target, ondelete=ondelete), nullable=False, **kwargs
        )
    )


def _timestamp(nullable: bool = False, **kwargs):
    if not nullable:
        kwargs.setdefault("server_default", func.now())
    return Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=nullable, **kwargs),
    )


class Role(SQLModel, table=True):
    __tablename__ = "role"

    id: int | None = _primary_key()
    name: str = Field(max_length=80, unique=True)
    created_at: datetime | None = _timestamp()
    updated_at: datetime | None = _timestamp(onupdate=func.now())


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
        CheckConstraint(_in("document_type", DocumentType), name="ck_user_account_document_type"),
    )

    id: int | None = _primary_key()
    email: str = Field(max_length=254, unique=True)
    full_name: str = Field(max_length=150)
    document_type: str = Field(max_length=3)
    document_number: str = Field(max_length=20)
    password_hash: str | None = Field(default=None, max_length=255)
    google_sub: str | None = Field(default=None, max_length=255, unique=True)
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": true()})
    role_id: int = _foreign_key("role.id", ondelete="RESTRICT")
    last_activity_at: datetime | None = _timestamp(nullable=True)
    created_at: datetime | None = _timestamp()
    updated_at: datetime | None = _timestamp(onupdate=func.now())

    role: Role = Relationship()


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_token"

    id: int | None = _primary_key()
    jti: str = Field(max_length=64, unique=True)
    user_id: int = _foreign_key("user_account.id", ondelete="CASCADE", index=True)
    issued_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = _timestamp(nullable=True)
    revoke_reason: str | None = Field(default=None, max_length=20)


class LoginAttempt(SQLModel, table=True):
    __tablename__ = "login_attempt"
    __table_args__ = (UniqueConstraint("identifier", "ip", name="uq_login_attempt_pair"),)

    id: int | None = _primary_key()
    identifier: str = Field(sa_column=Column(String(64), nullable=False))
    ip: str = Field(max_length=45)
    failures: int = Field(default=0)
    locked_until: datetime | None = _timestamp(nullable=True)
    updated_at: datetime | None = _timestamp(onupdate=func.now())


class LoginEvent(SQLModel, table=True):
    __tablename__ = "login_event"
    __table_args__ = (
        CheckConstraint(_in("method", LoginMethod), name="ck_login_event_method"),
        Index("ix_login_event_user_created", "user_id", "created_at"),
        Index("ix_login_event_created_at", "created_at"),
    )

    id: int | None = _primary_key()
    user_id: int = _foreign_key("user_account.id", ondelete="CASCADE")
    method: str = Field(max_length=10)
    ip: str = Field(max_length=45)
    created_at: datetime | None = _timestamp()
