import threading

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.accounts.errors import LastUserManager
from app.accounts.models import LoginEvent, RefreshToken, Role, RolePermission, UserAccount
from app.accounts.services import user_management
from tests.accounts.helpers import wait_until_blocked
from tests.factories import UserAccountFactory, use_session


def _delete_accounts(engine, user_ids: list[int]) -> None:
    with Session(engine) as cleanup:
        cleanup.exec(delete(RefreshToken).where(col(RefreshToken.user_id).in_(user_ids)))
        cleanup.exec(delete(LoginEvent).where(col(LoginEvent.user_id).in_(user_ids)))
        cleanup.exec(delete(UserAccount).where(col(UserAccount.id).in_(user_ids)))
        cleanup.commit()


def test_two_managers_deactivating_each_other_at_once_cannot_leave_nobody_in_charge(engine):
    """Corre con conexiones reales y datos confirmados: la espera por el bloqueo de filas solo
    ocurre entre transacciones distintas, así que el rollback de la prueba no sirve aquí."""
    with Session(engine) as setup:
        use_session(setup)
        administrator = setup.exec(select(Role).where(Role.name == "Administrador")).one()
        first, second = (UserAccountFactory(role=administrator) for _ in range(2))
        setup.commit()
        ids = [first.id, second.id]
        use_session(None)

    outcomes: dict[int, BaseException | None] = {}

    def deactivate(actor_id: int, target_id: int) -> None:
        with Session(engine) as session:
            try:
                actor = session.get(UserAccount, actor_id)
                user_management.deactivate_user(session, actor, target_id)
                outcomes[actor_id] = None
            except BaseException as error:  # noqa: BLE001
                outcomes[actor_id] = error

    try:
        threads = [
            threading.Thread(target=deactivate, args=(ids[0], ids[1])),
            threading.Thread(target=deactivate, args=(ids[1], ids[0])),
        ]
        with Session(engine) as holder:
            # Quien sostiene los bloqueos hace que las dos peticiones lleguen a la vez.
            holder.exec(
                select(UserAccount.id)
                .join(RolePermission, RolePermission.role_id == UserAccount.role_id)
                .where(RolePermission.permission == "users.manage", UserAccount.is_active)
                .order_by(UserAccount.id)
                .with_for_update(of=UserAccount)
            ).all()
            for thread in threads:
                thread.start()
            wait_until_blocked(engine, waiting=2)
            holder.rollback()

        for thread in threads:
            thread.join(timeout=10)

        assert not any(thread.is_alive() for thread in threads)
        errors = [outcome for outcome in outcomes.values() if outcome is not None]
        assert len(outcomes) == 2 and len(errors) == 1
        assert isinstance(errors[0], LastUserManager)
        with Session(engine) as check:
            statuses = check.exec(
                select(UserAccount.is_active).where(col(UserAccount.id).in_(ids))
            ).all()
        assert sorted(statuses) == [False, True]
    finally:
        _delete_accounts(engine, ids)
