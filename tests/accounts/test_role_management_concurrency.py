import threading

from sqlalchemy import delete, text
from sqlmodel import Session, col, select

from app.accounts.models import Role
from app.accounts.schemas import RoleInput
from app.accounts.services import role_management
from app.common.errors import InvalidFields
from tests.concurrency import wait_until_blocked

NAMES = ["Concurrencia uno", "Concurrencia dos"]


def test_two_roles_with_the_same_permissions_created_at_once_cannot_both_be_stored(engine):
    """Corre con conexiones reales: la espera por el bloqueo solo ocurre entre transacciones
    distintas, así que el rollback de la prueba no sirve aquí. Sin el bloqueo de escritura de
    roles las dos altas no se esperan y la prueba falla."""
    outcomes: dict[str, BaseException | None] = {}

    def create(name: str) -> None:
        with Session(engine) as session:
            try:
                data = RoleInput(name=name, permissions=["users.view", "roles.view"])
                role_management.create_role(session, data)
                outcomes[name] = None
            except BaseException as error:  # noqa: BLE001
                outcomes[name] = error

    try:
        threads = [threading.Thread(target=create, args=(name,)) for name in NAMES]
        with Session(engine) as holder:
            # Quien sostiene el bloqueo hace que las dos altas lleguen a la vez.
            holder.exec(
                text("SELECT pg_advisory_xact_lock(:key)").bindparams(
                    key=role_management.ROLE_WRITES_LOCK
                )
            )
            for thread in threads:
                thread.start()
            wait_until_blocked(engine, waiting=2)
            holder.rollback()

        for thread in threads:
            thread.join(timeout=10)

        assert not any(thread.is_alive() for thread in threads)
        errors = [outcome for outcome in outcomes.values() if outcome is not None]
        assert len(outcomes) == 2 and len(errors) == 1
        assert isinstance(errors[0], InvalidFields)
        assert "permissions" in errors[0].fields
        with Session(engine) as check:
            stored = check.exec(select(Role.name).where(col(Role.name).in_(NAMES))).all()
        assert len(stored) == 1
    finally:
        with Session(engine) as cleanup:
            cleanup.exec(delete(Role).where(col(Role.name).in_(NAMES)))
            cleanup.commit()
