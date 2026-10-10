import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-123")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from app.accounts.models import RolePermission  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import get_session  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security.cookies import ACCESS_COOKIE  # noqa: E402
from app.core.security.tokens import create_token  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.database import (  # noqa: E402
    admin_engine,
    create_database,
    drop_database,
    ensure_test_database_name,
)
from tests.factories import RoleFactory, UserAccountFactory, use_session  # noqa: E402
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
    use_session(session)
    yield session
    use_session(None)
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    # Los contadores del límite viven en memoria y pasarían de un test al siguiente.
    limiter.reset()


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


@pytest.fixture
def auth_client(client, session):
    """Fábrica de clientes con sesión y CSRF: auth_client(permissions=["clients.view"]).

    Crea un rol con esos permisos y una cuenta con ese rol, o usa la cuenta que se le pase.
    """

    def make(permissions: list[str] | tuple[str, ...] = (), user=None) -> TestClient:
        if user is None:
            role = RoleFactory()
            session.add_all(
                RolePermission(role_id=role.id, permission=code) for code in permissions
            )
            user = UserAccountFactory(role=role)
        session.flush()
        client.cookies.set(ACCESS_COOKIE, create_token(str(user.id), "access"), path="/api/")
        return attach_csrf(client)

    return make
