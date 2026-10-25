"""Lecturas de viajeros: lista con búsqueda y filtro por cliente de referencia, y ficha."""

from fastapi import Request
from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.clients.models import Traveler
from app.clients.schemas import TravelerFilters
from app.common.errors import NotFound
from app.common.identifiers import normalize_document
from app.common.pagination import Page, PageParams, paginate
from app.common.search import folded, has_every_word, starts_with


def _search(text: str) -> ColumnElement[bool]:
    full_name = col(Traveler.first_name) + " " + col(Traveler.last_name)
    by_name = has_every_word(full_name, text)
    document = normalize_document(text)
    if not document:
        return by_name
    return or_(by_name, starts_with(col(Traveler.document_number), document))


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
