"""Lecturas de cotizaciones: lista con búsqueda y filtros, y ficha con sus servicios."""

from fastapi import Request
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, col, select

from app.clients.models import Client
from app.clients.services.client_queries import display_name
from app.common.dates import today
from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, paginate
from app.common.search import has_every_word, name_or_document
from app.quotes.models import QUOTE_CODE, Quote, QuoteItem, QuoteStatus
from app.quotes.schemas import QuoteFilters, QuoteStatusFilter


def _search(text: str) -> ColumnElement[bool]:
    matching_clients = select(Client.id).where(
        or_(*name_or_document(display_name, col(Client.document_number), text))
    )
    conditions = [
        col(Quote.client_id).in_(matching_clients),
        has_every_word(col(Quote.destination), text),
    ]
    quote_id = QUOTE_CODE.parse(text)
    if quote_id is not None:
        conditions.append(col(Quote.id) == quote_id)
    return or_(*conditions)


def _status(status: QuoteStatusFilter) -> ColumnElement[bool]:
    expired = and_(col(Quote.status) == QuoteStatus.SENT, col(Quote.valid_until) < today())
    if status == QuoteStatusFilter.EXPIRED:
        return expired
    if status == QuoteStatusFilter.SENT:
        # Las vencidas tienen su propio filtro: "enviadas" son las que siguen vigentes.
        return and_(col(Quote.status) == QuoteStatus.SENT, col(Quote.valid_until) >= today())
    return col(Quote.status) == status


def list_quotes(
    session: Session, filters: QuoteFilters, params: PageParams, request: Request
) -> Page:
    statement = select(Quote)
    if filters.q:
        statement = statement.where(_search(filters.q))
    if filters.status is not None:
        statement = statement.where(_status(filters.status))
    if filters.client_id is not None:
        statement = statement.where(col(Quote.client_id) == filters.client_id)
    if filters.travel_request_id is not None:
        statement = statement.where(col(Quote.travel_request_id) == filters.travel_request_id)
    statement = statement.options(
        joinedload(Quote.client), joinedload(Quote.travel_request), joinedload(Quote.created_by)
    ).order_by(col(Quote.updated_at).desc(), col(Quote.id).desc())
    return paginate(session, statement, params, request)


def get_quote(session: Session, quote_id: int) -> Quote:
    quote = session.get(
        Quote,
        quote_id,
        options=[
            joinedload(Quote.client),
            joinedload(Quote.travel_request),
            joinedload(Quote.created_by),
            selectinload(Quote.items).options(
                joinedload(QuoteItem.supplier), joinedload(QuoteItem.tourist_service)
            ),
        ],
    )
    if quote is None:
        raise NotFound()
    return quote
