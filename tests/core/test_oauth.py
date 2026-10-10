import base64
import hashlib

import pytest
from itsdangerous import URLSafeTimedSerializer

from app.core.security import oauth
from app.core.security.redirects import safe_next_path


def test_pkce_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = oauth.new_pkce()

    digest = hashlib.sha256(verifier.encode()).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert 43 <= len(verifier) <= 128


def test_state_round_trip():
    data = {"state": "s", "nonce": "n", "verifier": "v", "next": "/clientes"}

    assert oauth.load_state(oauth.dump_state(data)) == data


@pytest.mark.parametrize("value", [None, "", "garbage", oauth.dump_state({"a": 1}) + "x"])
def test_missing_or_tampered_state_is_none(value):
    assert oauth.load_state(value) is None


def test_state_signed_with_another_key_is_none():
    forged = URLSafeTimedSerializer("y" * 32, salt="google-oauth").dumps({"state": "s"})

    assert oauth.load_state(forged) is None


def test_expired_state_is_none(monkeypatch):
    value = oauth.dump_state({"state": "s"})
    monkeypatch.setattr(oauth, "STATE_MAX_AGE_SECONDS", -1)

    assert oauth.load_state(value) is None


@pytest.mark.parametrize("path", ["/", "/clientes", "/cotizaciones/3?tab=pagos"])
def test_internal_paths_are_kept(path):
    assert safe_next_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "clientes",
        "//evil.example",
        "/\\evil.example",
        "https://evil.example",
        "/clientes\nSet-Cookie: x",
        "/clientes\t",
        "/" + "a" * 2001,
    ],
)
def test_anything_else_becomes_the_home_page(path):
    assert safe_next_path(path) == "/"
