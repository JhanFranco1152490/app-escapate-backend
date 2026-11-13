"""Lecturas de clientes: lista con búsqueda y filtros, y ficha."""

import re

from fastapi import Request
from sqlalchemy import ColumnElement, func, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.clients.models import Client
from app.clients.schemas import ClientFilters
from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, paginate
from app.common.search import contains, folded, name_or_document

_PHONE_SEPARATORS = re.compile(r"[\s\-().+]")
# Con menos dígitos casi cualquier teléfono coincidiría.
_PHONE_FRAGMENT = re.compile(r"[0-9]{3,}\Z")

# En una empresa los nombres son nulos, y "nulo || ' ' || nulo" también: queda la razón social.
# Público: otros dominios buscan por el nombre del cliente con la misma expresión.
display_name = func.coalesce(
    col(Client.first_name) + " " + col(Client.last_name), col(Client.business_name)
)


def _search(text: str) -> ColumnElement[bool]:
    conditions = name_or_document(display_name, col(Client.document_number), text)
    conditions.append(contains(col(Client.email), text.lower()))
    phone = _PHONE_SEPARATORS.sub("", text)
    if _PHONE_FRAGMENT.match(phone):
        conditions.append(contains(col(Client.phone), phone))
    return or_(*conditions)


def list_clients(
    session: Session, filters: ClientFilters, params: PageParams, request: Request
) -> Page:
    statement = select(Client)
    if filters.q:
        statement = statement.where(_search(filters.q))
    if filters.client_type is not None:
        statement = statement.where(Client.client_type == filters.client_type)
    statement = statement.order_by(folded(display_name), Client.id)
    return paginate(session, statement, params, request)


def get_client(session: Session, client_id: int) -> Client:
    client = session.get(
        Client,
        client_id,
        options=[joinedload(Client.created_by), joinedload(Client.data_consent_by)],
    )
    if client is None:
        raise NotFound()
    return client
