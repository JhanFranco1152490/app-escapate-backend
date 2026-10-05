import pytest
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, literal_column
from sqlmodel import Session, select

from app.common.pagination import Page, PageParams, page_params, paginate
from app.core.db import get_session

router = APIRouter(prefix="/api/test")


def numbers(total: int):
    series = func.generate_series(1, total).alias("n")
    return select(literal_column("n")).select_from(series).order_by(literal_column("n"))


@router.get("/numbers", response_model=Page[int])
def list_numbers(
    request: Request,
    total: int = 45,
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
):
    return paginate(session, numbers(total), params, request)


@pytest.fixture
def client(app, client):
    app.include_router(router)
    return client


def test_first_page_uses_the_default_size(client):
    body = client.get("/api/test/numbers").json()

    assert body["count"] == 45
    assert body["results"] == list(range(1, 21))
    assert body["previous"] is None
    assert "page=2" in body["next"]


def test_last_page_has_the_remainder_and_no_next(client):
    body = client.get("/api/test/numbers?page=3").json()

    assert body["results"] == [41, 42, 43, 44, 45]
    assert body["next"] is None
    assert "page=2" in body["previous"]


@pytest.mark.parametrize("page", [0, -1, 4])
def test_out_of_range_page_is_not_found(client, page):
    response = client.get(f"/api/test/numbers?page={page}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_page_size_above_the_limit_is_clipped(client):
    body = client.get("/api/test/numbers?total=150&page_size=500").json()

    assert len(body["results"]) == 100


def test_zero_page_size_is_invalid(client):
    response = client.get("/api/test/numbers?page_size=0")

    assert response.status_code == 422
    assert "page_size" in response.json()["fields"]


def test_empty_list_is_a_valid_first_page(client):
    response = client.get("/api/test/numbers?total=0")

    assert response.status_code == 200
    assert response.json() == {"count": 0, "next": None, "previous": None, "results": []}


def test_links_keep_the_other_query_parameters(client):
    body = client.get("/api/test/numbers?total=45&page=2").json()

    assert "total=45" in body["next"]
    assert "total=45" in body["previous"]
