from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.security.passwords import hash_password, verify_password


def test_hash_does_not_contain_the_password():
    password_hash = hash_password("una clave larga")

    assert "una clave larga" not in password_hash
    assert password_hash.startswith("$argon2id$")


def test_correct_password_is_verified_without_rehash():
    password_hash = hash_password("una clave larga")

    assert verify_password("una clave larga", password_hash) == (True, None)


def test_wrong_password_is_rejected():
    password_hash = hash_password("una clave larga")

    valid, _ = verify_password("otra clave", password_hash)

    assert valid is False


def test_hash_with_old_parameters_is_upgraded_on_login():
    old = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192),)).hash("una clave larga")

    valid, new_hash = verify_password("una clave larga", old)

    assert valid is True
    assert new_hash is not None
    assert verify_password("una clave larga", new_hash) == (True, None)
