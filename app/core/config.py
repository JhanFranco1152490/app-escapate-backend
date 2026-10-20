from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PSYCOPG_SCHEME = "postgresql+psycopg://"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://app_escapate:app_escapate@localhost:5432/app_escapate"
    )
    test_database_url: str = (
        "postgresql+psycopg://app_escapate:app_escapate@localhost:5432/app_escapate_test"
    )
    secret_key: str
    debug: bool = False
    frontend_origin: str = "http://localhost:3000"
    trusted_proxy_count: int = 0
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    email_backend: Literal["console", "resend"] = "console"
    email_from: str = "Escápate <no-responder@example.com>"
    resend_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    rate_login: str = "10/minute"
    rate_google: str = "20/minute"
    rate_refresh: str = "120/minute"
    rate_password_reset: str = "5/hour"
    rate_password_reset_confirm: str = "20/hour"
    rate_user_invitation: str = "10/hour"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        # Los proveedores entregan la URL como postgres:// o postgresql://, y SQLAlchemy
        # necesita el nombre del driver explícito para usar psycopg 3.
        for scheme in ("postgres://", "postgresql://"):
            if value.startswith(scheme):
                return _PSYCOPG_SCHEME + value.removeprefix(scheme)
        return value

    @field_validator("secret_key")
    @classmethod
    def secret_key_is_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY debe tener al menos 32 caracteres")
        return value


settings = Settings()
