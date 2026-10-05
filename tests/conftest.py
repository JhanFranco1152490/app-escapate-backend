import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-123")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.database import (  # noqa: E402
    admin_engine,
    create_database,
    drop_database,
    ensure_test_database_name,
)
from tests.http import attach_csrf  # noqa: E402

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def engine():
    url = make_url(settings.test_database_url)
    name = ensure_test_database_name(url)
    admin = admin_engine(url)
    create_database(admin, name)

    engine = create_engine(url)
    with engine.begin() as connection:
        config = Config(str(ALEMBIC_INI))
        config.attributes["connection"] = connection
        # Subir, bajar y volver a subir prueba también que cada migración se puede revertir.
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    yield engine

    engine.dispose()
    drop_database(admin, name)
    admin.dispose()


@pytest.fixture
def session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    # El commit() de los servicios libera un savepoint, no la transacción de la prueba.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def app(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return app


@pytest.fixture
def client(app):
    # https para que las cookies Secure viajen igual que en producción.
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=False)


@pytest.fixture
def csrf_client(client):
    """Cliente sin sesión pero con token CSRF: para probar mutaciones."""
    return attach_csrf(client)
