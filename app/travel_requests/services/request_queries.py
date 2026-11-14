"""Lecturas de solicitudes de viaje: lista con búsqueda y filtros, ficha y resumen."""

from datetime import timedelta

from fastapi import Request
from sqlalchemy import ColumnElement, Date, and_, cast, func, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.clients.models import Client
from app.clients.services.client_queries import display_name
from app.common.dates import BOGOTA, today
from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, paginate
from app.common.search import has_every_word, name_or_document
from app.travel_requests.codes import parse_code
from app.travel_requests.models import PENDING_STATUSES, TravelRequest, TravelRequestStatus
from app.travel_requests.schemas import (
    RequestSort,
    StatusCounts,
    StatusFilter,
    SummaryFilters,
    TravelRequestFilters,
    TravelRequestSummary,
)

# Una solicitud pendiente que lleva más de estos días sin cotizar se cuenta aparte.
PENDING_WAIT_DAYS = 3

_ORDER = {
    RequestSort.RECENT: (col(TravelRequest.updated_at).desc(), col(TravelRequest.id).desc()),
    RequestSort.OLDEST: (col(TravelRequest.created_at), col(TravelRequest.id)),
}


def _search(text: str) -> ColumnElement[bool]:
    matching_clients = select(Client.id).where(
        or_(*name_or_document(display_name, col(Client.document_number), text))
    )
    conditions = [
        col(TravelRequest.client_id).in_(matching_clients),
        has_every_word(col(TravelRequest.destination), text),
    ]
    request_id = parse_code(text)
    if request_id is not None:
        conditions.append(col(TravelRequest.id) == request_id)
    return or_(*conditions)


def _status(status: StatusFilter) -> ColumnElement[bool]:
    if status == StatusFilter.PENDING:
        return col(TravelRequest.status).in_(PENDING_STATUSES)
    return col(TravelRequest.status) == status


def _belongs_to(filters: TravelRequestFilters | SummaryFilters) -> list[ColumnElement[bool]]:
    conditions = []
    if filters.assigned_to is not None:
        conditions.append(col(TravelRequest.assigned_to_id) == filters.assigned_to)
    if filters.client_id is not None:
        conditions.append(col(TravelRequest.client_id) == filters.client_id)
    return conditions


def list_requests(
    session: Session, filters: TravelRequestFilters, params: PageParams, request: Request
) -> Page:
    statement = select(TravelRequest).where(*_belongs_to(filters))
    if filters.q:
        statement = statement.where(_search(filters.q))
    if filters.status is not None:
        statement = statement.where(_status(filters.status))
    statement = statement.options(
        joinedload(TravelRequest.client), joinedload(TravelRequest.assigned_to)
    ).order_by(*_ORDER[filters.sort])
    return paginate(session, statement, params, request)


def get_request(session: Session, request_id: int) -> TravelRequest:
    travel_request = session.get(
        TravelRequest,
        request_id,
        options=[
            joinedload(TravelRequest.client),
            joinedload(TravelRequest.assigned_to),
            joinedload(TravelRequest.created_by),
            joinedload(TravelRequest.closed_by),
        ],
    )
    if travel_request is None:
        raise NotFound()
    return travel_request


def request_summary(session: Session, filters: SummaryFilters) -> TravelRequestSummary:
    pending = col(TravelRequest.status).in_(PENDING_STATUSES)
    # El día en Bogotá en que se registró, igual que los días de espera de cada solicitud.
    registered_on = cast(func.timezone(BOGOTA.key, TravelRequest.created_at), Date)
    waiting_too_long = and_(pending, registered_on < today() - timedelta(days=PENDING_WAIT_DAYS))

    def count(condition: ColumnElement[bool]):
        return func.count().filter(condition)

    by_status = {
        status.value: count(col(TravelRequest.status) == status) for status in TravelRequestStatus
    }
    row = session.exec(
        select(
            *(column.label(name) for name, column in by_status.items()),
            func.count().label("total"),
            count(pending).label("pending"),
            count(waiting_too_long).label("pending_over_3_days"),
        ).where(*_belongs_to(filters))
    ).one()
    return TravelRequestSummary(
        by_status=StatusCounts(**{name: getattr(row, name) for name in by_status}),
        total=row.total,
        pending=row.pending,
        pending_over_3_days=row.pending_over_3_days,
    )
