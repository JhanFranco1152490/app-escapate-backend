"""Lecturas de viajeros: lista con búsqueda y filtro por cliente de referencia, y ficha."""

from fastapi import Request
from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.clients.models import Traveler
from app.clients.schemas import TravelerFilters
from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, paginate
from app.common.search import folded, name_or_document


def _search(text: str) -> ColumnElement[bool]:
    full_name = col(Traveler.first_name) + " " + col(Traveler.last_name)
    return or_(*name_or_document(full_name, col(Traveler.document_number), text))


def list_travelers(
    session: Session, filters: TravelerFilters, params: PageParams, request: Request
) -> Page:
    statement = select(Traveler).options(joinedload(Traveler.reference_client))
    if filters.q:
        statement = statement.where(_search(filters.q))
    if filters.client_id is not None:
        statement = statement.where(Traveler.reference_client_id == filters.client_id)
    statement = statement.order_by(
        folded(Traveler.first_name), folded(Traveler.last_name), Traveler.id
    )
    return paginate(session, statement, params, request)


def get_traveler(session: Session, traveler_id: int) -> Traveler:
    traveler = session.get(
        Traveler,
        traveler_id,
        options=[
            joinedload(Traveler.reference_client),
            joinedload(Traveler.created_by),
            joinedload(Traveler.data_consent_by),
        ],
    )
    if traveler is None:
        raise NotFound()
    return traveler
