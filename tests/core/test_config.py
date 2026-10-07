import pytest

from app.core.config import Settings

SECRET = "x" * 32


@pytest.mark.parametrize(
    "raw",
    ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db"],
)
def test_database_url_is_normalized_to_psycopg(raw):
    settings = Settings(secret_key=SECRET, database_url=raw)

    assert settings.database_url == "postgresql+psycopg://u:p@h:5432/db"


def test_psycopg_url_is_kept_as_is():
    url = "postgresql+psycopg://u:p@h:5432/db"

    assert Settings(secret_key=SECRET, database_url=url).database_url == url


def test_short_secret_key_is_rejected():
    with pytest.raises(ValueError):
        Settings(secret_key="short")
