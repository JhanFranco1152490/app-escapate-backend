from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.accounts.models import LoginEvent, RefreshToken
from app.accounts.services import sessions
from app.common.errors import AuthenticationFailed
from app.core.security.tokens import create_token, decode_token
from tests.factories import UserAccountFactory

IP = "203.0.113.7"


def now() -> datetime:
    return datetime.now(UTC)


def tokens_of(session, user) -> list[RefreshToken]:
    statement = select(RefreshToken).where(RefreshToken.user_id == user.id)
    return list(session.exec(statement.order_by(RefreshToken.id)).all())


def active(session, user) -> list[RefreshToken]:
    return [token for token in tokens_of(session, user) if token.revoked_at is None]


def jti_of(refresh: str) -> str:
    return decode_token(refresh, "refresh")["jti"]


def open_for(session, user, method="document"):
    pair = sessions.open_session(session, user, method, IP)
    session.commit()
    return pair


def test_open_session_issues_tokens_and_records_the_login(session):
    user = UserAccountFactory()

    pair = open_for(session, user, method="google")

    assert decode_token(pair.access, "access")["sub"] == str(user.id)
    assert [token.jti for token in active(session, user)] == [jti_of(pair.refresh)]
    event = session.exec(select(LoginEvent).where(LoginEvent.user_id == user.id)).one()
    assert (event.method, event.ip) == ("google", IP)
    assert user.last_activity_at is not None


def test_a_fourth_session_closes_the_oldest(session):
    user = UserAccountFactory()
    first, second, third = (open_for(session, user) for _ in range(3))

    fourth = open_for(session, user)

    remaining = {token.jti for token in active(session, user)}
    assert remaining == {jti_of(pair.refresh) for pair in (second, third, fourth)}
    oldest = next(t for t in tokens_of(session, user) if t.jti == jti_of(first.refresh))
    assert oldest.revoke_reason == "session_limit"


def test_sessions_of_other_accounts_do_not_count(session):
    user, other = UserAccountFactory(), UserAccountFactory()
    for _ in range(3):
        open_for(session, other)

    open_for(session, user)

    assert len(active(session, other)) == 3


def test_expired_refresh_tokens_are_deleted_on_login(session):
    user = UserAccountFactory()
    open_for(session, user)
    expired = tokens_of(session, user)[0]
    expired.expires_at = now() - timedelta(seconds=1)
    expired_jti = expired.jti
    session.commit()

    open_for(session, user)

    assert expired_jti not in {token.jti for token in tokens_of(session, user)}


def test_login_events_older_than_90_days_are_deleted(session):
    other = UserAccountFactory()
    old = LoginEvent(user_id=other.id, method="document", ip=IP)
    recent = LoginEvent(user_id=other.id, method="document", ip=IP)
    old.created_at = now() - timedelta(days=90, minutes=1)
    recent.created_at = now() - timedelta(days=89)
    session.add_all([old, recent])
    session.commit()

    open_for(session, UserAccountFactory())

    remaining = session.exec(select(LoginEvent.id).where(LoginEvent.user_id == other.id)).all()
    assert remaining == [recent.id]


def test_rotate_revokes_the_old_token_and_issues_a_new_pair(session):
    user = UserAccountFactory()
    pair = open_for(session, user)
    user.last_activity_at = now() - timedelta(hours=1)
    session.commit()

    new_pair = sessions.rotate(session, pair.refresh)

    old = next(t for t in tokens_of(session, user) if t.jti == jti_of(pair.refresh))
    assert old.revoke_reason == "rotated"
    assert [token.jti for token in active(session, user)] == [jti_of(new_pair.refresh)]
    assert user.last_activity_at > now() - timedelta(minutes=1)


def rotated_seconds_ago(session, user, refresh: str, seconds: int) -> None:
    token = next(t for t in tokens_of(session, user) if t.jti == jti_of(refresh))
    token.revoked_at = now() - timedelta(seconds=seconds)
    session.commit()


def test_reusing_a_rotated_token_revokes_every_session(session):
    user = UserAccountFactory()
    stolen = open_for(session, user)
    open_for(session, user)
    sessions.rotate(session, stolen.refresh)
    rotated_seconds_ago(session, user, stolen.refresh, 31)

    with pytest.raises(AuthenticationFailed):
        sessions.rotate(session, stolen.refresh)

    assert active(session, user) == []
    assert "reuse_detected" in {token.revoke_reason for token in tokens_of(session, user)}


def test_reusing_a_token_rotated_seconds_ago_only_fails(session):
    user = UserAccountFactory()
    pair = open_for(session, user)
    sessions.rotate(session, pair.refresh)
    rotated_seconds_ago(session, user, pair.refresh, 5)

    with pytest.raises(AuthenticationFailed):
        sessions.rotate(session, pair.refresh)

    assert len(active(session, user)) == 1


@pytest.mark.parametrize("reason", ["logout", "session_limit"])
def test_a_token_closed_for_other_reasons_only_fails(session, reason):
    user = UserAccountFactory()
    closed = open_for(session, user)
    open_for(session, user)
    token = next(t for t in tokens_of(session, user) if t.jti == jti_of(closed.refresh))
    token.revoked_at, token.revoke_reason = now() - timedelta(hours=1), reason
    session.commit()

    with pytest.raises(AuthenticationFailed):
        sessions.rotate(session, closed.refresh)

    assert len(active(session, user)) == 1


def test_rotate_fails_for_an_inactive_account(session):
    user = UserAccountFactory()
    pair = open_for(session, user)
    user.is_active = False
    session.commit()

    with pytest.raises(AuthenticationFailed):
        sessions.rotate(session, pair.refresh)


@pytest.mark.parametrize(
    "refresh",
    [
        pytest.param(lambda user: create_token(str(user.id), "refresh", jti="unknown"), id="jti"),
        pytest.param(lambda user: create_token(str(user.id), "refresh"), id="without-jti"),
        pytest.param(lambda user: create_token(str(user.id), "access"), id="access-token"),
        pytest.param(lambda user: "garbage", id="garbage"),
    ],
)
def test_rotate_rejects_tokens_it_did_not_issue(session, refresh):
    user = UserAccountFactory()

    with pytest.raises(AuthenticationFailed):
        sessions.rotate(session, refresh(user))


def test_revoke_closes_only_that_session(session):
    user = UserAccountFactory()
    pair, other = open_for(session, user), open_for(session, user)

    sessions.revoke(session, pair.refresh, "logout")

    assert [token.jti for token in active(session, user)] == [jti_of(other.refresh)]


def test_revoke_ignores_invalid_tokens(session):
    sessions.revoke(session, "garbage", "logout")
