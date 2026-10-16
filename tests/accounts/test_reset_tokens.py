import base64
import json
import time
from datetime import timedelta
from types import SimpleNamespace

import itsdangerous
import itsdangerous.timed
import pytest

from app.accounts.errors import InvalidResetToken
from app.accounts.services.reset_tokens import TokenPurpose, make_token, read_token
from tests.factories import UserAccountFactory

RESET, INVITATION = TokenPurpose.RESET, TokenPurpose.INVITATION


def issued_ago(monkeypatch, user, purpose, age: timedelta) -> str:
    """Token emitido hace `age`: solo el reloj de itsdangerous retrocede, y solo al firmar."""
    issued_at = time.time() - age.total_seconds()
    with monkeypatch.context() as patch:
        patch.setattr(itsdangerous.timed, "time", SimpleNamespace(time=lambda: issued_at))
        return make_token(user, purpose)


@pytest.mark.parametrize("purpose", [RESET, INVITATION])
def test_a_fresh_token_identifies_the_account_and_purpose(session, purpose):
    user = UserAccountFactory()

    assert read_token(session, make_token(user, purpose)) == (user, purpose)


@pytest.mark.parametrize(
    "purpose, still_valid, expired",
    [
        (RESET, timedelta(minutes=29), timedelta(minutes=31)),
        (INVITATION, timedelta(hours=71), timedelta(hours=73)),
    ],
)
def test_each_purpose_has_its_own_lifetime(session, monkeypatch, purpose, still_valid, expired):
    user = UserAccountFactory()

    assert read_token(session, issued_ago(monkeypatch, user, purpose, still_valid))[0] == user
    with pytest.raises(InvalidResetToken):
        read_token(session, issued_ago(monkeypatch, user, purpose, expired))


@pytest.mark.parametrize("purpose", [RESET, INVITATION])
def test_the_purpose_comes_from_the_signature_and_cannot_be_swapped(session, purpose):
    # Cada propósito firma con su propio salt: un enlace de invitación (72 h) nunca se lee
    # como uno de recuperación (30 min), ni al revés.
    user = UserAccountFactory()

    assert read_token(session, make_token(user, purpose))[1] == purpose


def test_tampered_or_foreign_tokens_are_rejected(session):
    user = UserAccountFactory()
    token = make_token(user, RESET)
    foreign = itsdangerous.URLSafeTimedSerializer("y" * 32, salt="password-reset").dumps(
        {"u": user.id, "f": "x"}
    )

    for candidate in (token[:-2] + "xx", foreign, "garbage", ""):
        with pytest.raises(InvalidResetToken):
            read_token(session, candidate)


def test_the_token_stops_working_after_a_password_change(session):
    user = UserAccountFactory()
    token = make_token(user, RESET)

    user.password_hash = "otro-hash"
    session.flush()

    with pytest.raises(InvalidResetToken):
        read_token(session, token)


def test_the_token_stops_working_after_an_email_change(session):
    user = UserAccountFactory(email="antes@example.com")
    token = make_token(user, INVITATION)

    user.email = "despues@example.com"
    session.flush()

    with pytest.raises(InvalidResetToken):
        read_token(session, token)


def test_an_invited_account_without_password_gets_a_working_token(session):
    user = UserAccountFactory(password_hash=None)

    assert read_token(session, make_token(user, INVITATION))[0] == user


def test_tokens_of_inactive_or_deleted_accounts_are_rejected(session):
    inactive = UserAccountFactory(is_active=False)
    deleted = UserAccountFactory()
    deleted_token = make_token(deleted, RESET)
    session.delete(deleted)
    session.flush()

    for token in (make_token(inactive, RESET), deleted_token):
        with pytest.raises(InvalidResetToken):
            read_token(session, token)


def test_the_readable_payload_has_neither_email_nor_hash(session):
    user = UserAccountFactory(email="persona.secreta@example.com")
    token = make_token(user, RESET)

    encoded = token.split(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))

    assert set(payload) == {"u", "f"}
    assert "persona.secreta" not in token
    assert user.password_hash not in json.dumps(payload)
