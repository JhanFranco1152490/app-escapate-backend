from datetime import UTC, datetime

from sqlmodel import select

from app.accounts.models import LoginAttempt
from app.accounts.services import lockout


def rows(session) -> list[tuple[str, str]]:
    statement = select(LoginAttempt.identifier, LoginAttempt.ip).order_by(LoginAttempt.ip)
    return [tuple(row) for row in session.exec(statement).all()]


def test_clearing_a_document_removes_its_locks_in_every_ip(session):
    now = datetime.now(UTC)
    mine = lockout.lock_identifier("CC", "1090123456")
    other = lockout.lock_identifier("CC", "1090999999")
    for ip in ("198.51.100.1", "198.51.100.2"):
        lockout.register_failure(session, mine, ip, now)
    lockout.register_failure(session, other, "198.51.100.1", now)

    lockout.clear_document_locks(session, mine)

    assert rows(session) == [(other, lockout.ANY_IP), (other, "198.51.100.1")]


def test_a_failure_counts_for_the_ip_and_for_the_document(session):
    identifier = lockout.lock_identifier("CC", "1090123456")

    lockout.register_failure(session, identifier, "198.51.100.1", datetime.now(UTC))

    assert rows(session) == [(identifier, lockout.ANY_IP), (identifier, "198.51.100.1")]
