import pytest
from sqlalchemy.engine import make_url

from tests.database import ensure_test_database_name

BASE = "postgresql+psycopg://u:p@localhost:5432/"


def test_accepts_a_name_ending_in_test():
    assert ensure_test_database_name(make_url(BASE + "app_escapate_test")) == "app_escapate_test"


@pytest.mark.parametrize("name", ["app_escapate", "app_escapate_test_x", "test", "App_test"])
def test_rejects_names_that_could_be_a_real_database(name):
    with pytest.raises(RuntimeError):
        ensure_test_database_name(make_url(BASE + name))


def test_rejects_a_trailing_newline():
    url = make_url(BASE + "app_escapate").set(database="app_escapate_test\n")

    with pytest.raises(RuntimeError):
        ensure_test_database_name(url)
