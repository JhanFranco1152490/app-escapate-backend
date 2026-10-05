from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.common.errors import AuthenticationFailed
from app.core.config import settings
from app.core.security.tokens import create_token, decode_token


def encode(payload: dict, key: str = "") -> str:
    return jwt.encode(payload, key or settings.secret_key, algorithm="HS256")


def test_token_round_trip_keeps_subject_and_jti():
    token = create_token("42", "refresh", jti="abc")

    payload = decode_token(token, "refresh")

    assert payload["sub"] == "42"
    assert payload["jti"] == "abc"


def test_access_token_has_no_jti():
    assert "jti" not in decode_token(create_token("42", "access"), "access")


def expired() -> str:
    past = datetime.now(UTC) - timedelta(minutes=1)
    return encode({"sub": "42", "type": "access", "exp": past})


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: create_token("42", "refresh"), id="refresh-as-access"),
        pytest.param(expired, id="expired"),
        pytest.param(
            lambda: encode(
                {"sub": "42", "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=1)},
                key="y" * 32,
            ),
            id="other-key",
        ),
        pytest.param(lambda: encode({"sub": "42", "type": "access"}), id="without-exp"),
        pytest.param(lambda: "abc", id="garbage"),
        pytest.param(lambda: "", id="empty"),
    ],
)
def test_invalid_access_tokens_fail_authentication(token):
    with pytest.raises(AuthenticationFailed):
        decode_token(token(), "access")
