import threading

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.accounts.errors import InvalidResetToken
from app.accounts.models import LoginAttempt, LoginEvent, RefreshToken, Role, UserAccount
from app.accounts.services import lockout, password_reset
from app.accounts.services.reset_tokens import TokenPurpose, make_token
from app.core.security.passwords import hash_password
from tests.concurrency import wait_until_blocked
from tests.factories import UserAccountFactory, use_session

DOCUMENT = "1090555444"
NEW_PASSWORD = "una frase nueva y larga"


def _delete_everything_of(engine, user_id: int, role_id: int) -> None:
    with Session(engine) as cleanup:
        cleanup.exec(delete(RefreshToken).where(col(RefreshToken.user_id) == user_id))
        cleanup.exec(delete(LoginEvent).where(col(LoginEvent.user_id) == user_id))
        identifier = lockout.lock_identifier("CC", DOCUMENT)
        cleanup.exec(delete(LoginAttempt).where(col(LoginAttempt.identifier) == identifier))
        cleanup.exec(delete(UserAccount).where(col(UserAccount.id) == user_id))
        cleanup.exec(delete(Role).where(col(Role.id) == role_id))
        cleanup.commit()


def test_a_second_submission_waiting_on_the_account_lock_cannot_reuse_the_link(engine):
    """Corre con conexiones reales y datos confirmados: el rollback de la prueba no sirve aquí,
    porque la espera por el bloqueo de fila solo ocurre entre transacciones distintas."""
    with Session(engine) as setup:
        use_session(setup)
        user = UserAccountFactory(document_number=DOCUMENT)
        setup.commit()
        user_id, role_id = user.id, user.role_id
        token = make_token(user, TokenPurpose.RESET)
        use_session(None)

    outcome: dict[str, BaseException | None] = {"error": None}

    def second_submission() -> None:
        with Session(engine) as session:
            try:
                password_reset.confirm(session, token, NEW_PASSWORD, NEW_PASSWORD, "::1")
            except BaseException as error:  # noqa: BLE001
                outcome["error"] = error

    try:
        with Session(engine) as first:
            # La primera petición ya tiene la fila de la cuenta bloqueada.
            holder = first.exec(
                select(UserAccount).where(UserAccount.id == user_id).with_for_update()
            ).one()
            waiter = threading.Thread(target=second_submission)
            waiter.start()
            wait_until_blocked(engine, waiting=1)

            # La primera termina: cambia la contraseña, que invalida el enlace, y libera la fila.
            holder.password_hash = hash_password("la contraseña que dejó la primera")
            first.commit()

        waiter.join(timeout=10)

        assert not waiter.is_alive()
        assert isinstance(outcome["error"], InvalidResetToken)
    finally:
        _delete_everything_of(engine, user_id, role_id)
