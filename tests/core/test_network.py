import pytest
from starlette.requests import Request

from app.core.config import settings
from app.core.security.network import client_ip

DIRECT = "9.9.9.9"


def request_with(forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request({"type": "http", "headers": headers, "client": (DIRECT, 1234)})


@pytest.fixture
def proxies(monkeypatch):
    def set_count(count: int) -> None:
        monkeypatch.setattr(settings, "trusted_proxy_count", count)

    return set_count


def test_without_proxies_the_forwarded_header_is_ignored(proxies):
    proxies(0)

    assert client_ip(request_with("1.1.1.1")) == DIRECT


def test_behind_one_proxy_the_last_entry_is_the_client(proxies):
    proxies(1)

    # La primera entrada la pudo escribir el cliente; la última la agregó el proxy.
    assert client_ip(request_with("1.1.1.1, 2.2.2.2")) == "2.2.2.2"


def test_behind_two_proxies_the_second_from_the_right_is_the_client(proxies):
    proxies(2)

    assert client_ip(request_with("1.1.1.1, 2.2.2.2, 3.3.3.3")) == "2.2.2.2"


@pytest.mark.parametrize("forwarded", [None, "", " , "])
def test_behind_a_proxy_without_entries_falls_back_to_the_connection(proxies, forwarded):
    proxies(1)

    assert client_ip(request_with(forwarded)) == DIRECT


def test_fewer_entries_than_proxies_falls_back_to_the_connection(proxies):
    proxies(2)

    assert client_ip(request_with("2.2.2.2")) == DIRECT
