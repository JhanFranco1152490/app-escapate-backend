import pytest
from fastapi import APIRouter, Request

from app.core.rate_limit import limiter
from app.core.security.csrf import CSRF_HEADER
from tests.http import attach_csrf

router = APIRouter(prefix="/api/test")


@router.post("/limited")
@limiter.limit("2/minute")
def limited(request: Request):
    return {"ok": True}


@pytest.fixture
def client(app, client):
    app.include_router(router)
    return client


def test_requests_over_the_limit_are_throttled(client):
    attach_csrf(client)

    statuses = [client.post("/api/test/limited").status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_throttled_response_uses_the_common_shape(client):
    attach_csrf(client)
    for _ in range(2):
        client.post("/api/test/limited")

    response = client.post("/api/test/limited")

    assert response.json()["code"] == "throttled"
    assert response.json()["fields"] == {}


def test_requests_rejected_by_csrf_do_not_use_the_quota(client):
    for _ in range(3):
        assert client.post("/api/test/limited").status_code == 403

    attach_csrf(client)

    assert client.post("/api/test/limited").status_code == 200


def test_limits_do_not_leak_between_tests_first(client):
    attach_csrf(client)

    assert [client.post("/api/test/limited").status_code for _ in range(2)] == [200, 200]


def test_limits_do_not_leak_between_tests_second(client):
    attach_csrf(client)

    assert client.post("/api/test/limited").status_code == 200
    assert CSRF_HEADER in client.headers
