from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app_user:app_password@localhost:5432/app_escapate"
    secret_key: str = "change-me"
    debug: bool = False


settings = Settings()
