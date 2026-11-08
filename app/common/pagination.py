from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from fastapi import Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.sql import Select
from sqlmodel import Session, select

from app.common.errors import NotFound

T = TypeVar("T")
MAX_PAGE_SIZE = 100


class Page(BaseModel, Generic[T]):
    count: int
    next: str | None
    previous: str | None
    results: list[T]


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int


def page_params(page: int = Query(1), page_size: int = Query(20, ge=1)) -> PageParams:
    # page sin ge=1: una página menor que 1 está fuera de rango (404), no es un dato inválido.
    if page < 1:
        raise NotFound()
    return PageParams(page=page, page_size=min(page_size, MAX_PAGE_SIZE))


def paginate(session: Session, statement: Select, params: PageParams, request: Request) -> Page:
    count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    offset = (params.page - 1) * params.page_size
    if params.page > 1 and offset >= count:
        raise NotFound()
    rows = session.exec(statement.offset(offset).limit(params.page_size)).all()
    has_next = offset + params.page_size < count
    return Page(
        count=count,
        next=_page_url(request, params.page + 1) if has_next else None,
        previous=_page_url(request, params.page - 1) if params.page > 1 else None,
        results=list(rows),
    )


def map_results(page: Page, transform: Callable[[Any], Any]) -> Page:
    """La misma página con cada fila transformada: para las listas que traen una columna
    calculada junto con el modelo y arman con las dos el esquema de salida."""
    return page.model_copy(update={"results": [transform(row) for row in page.results]})


def _page_url(request: Request, page: int) -> str:
    return str(request.url.include_query_params(page=page))
