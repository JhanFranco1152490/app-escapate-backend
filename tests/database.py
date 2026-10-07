import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

TEST_DB_NAME = re.compile(r"[a-z0-9_]+_test\Z")


def ensure_test_database_name(url: URL) -> str:
    # La base de pruebas se borra al empezar y al terminar: un TEST_DATABASE_URL mal puesto
    # no puede apuntar a la base de desarrollo.
    name = url.database or ""
    if not TEST_DB_NAME.match(name):
        raise RuntimeError("TEST_DATABASE_URL debe apuntar a una base terminada en _test")
    return name


def admin_engine(url: URL) -> Engine:
    return create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")


def drop_database(admin: Engine, name: str) -> None:
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def create_database(admin: Engine, name: str) -> None:
    drop_database(admin, name)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
