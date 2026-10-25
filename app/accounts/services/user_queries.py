"""Lecturas de usuarios para la gestión: lista con búsqueda y filtros, ficha e ingresos."""

from fastapi import Request
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.accounts.models import LoginEvent, UserAccount
from app.accounts.schemas import UserFilters
from app.common.errors import NotFound
from app.common.identifiers import normalize_document
from app.common.pagination import Page, PageParams, paginate
from app.common.search import folded

# Más palabras que esto no cambian de forma útil el resultado y alargan la consulta.
MAX_SEARCH_WORDS = 5
_ESCAPE = "\\"


def _escape_like(text: str) -> str:
    """Hace literales los comodines de LIKE, para que lo escrito se busque tal cual."""
    return (
        text.replace(_ESCAPE, _ESCAPE * 2).replace("%", f"{_ESCAPE}%").replace("_", f"{_ESCAPE}_")
    )


def _search(text: str) -> ColumnElement[bool]:
    full_name = col(UserAccount.first_name) + " " + col(UserAccount.last_name)
    words = text.split()[:MAX_SEARCH_WORDS]
    by_name = and_(
        *(
            folded(full_name).like(folded(f"%{_escape_like(word)}%"), escape=_ESCAPE)
            for word in words
        )
    )
    document = normalize_document(text)
    if not document:
        return by_name
    by_document = col(UserAccount.document_number).like(
        f"{_escape_like(document)}%", escape=_ESCAPE
    )
    return or_(by_name, by_document)


def list_users(
    session: Session, filters: UserFilters, params: PageParams, request: Request
) -> Page:
    statement = select(UserAccount).options(joinedload(UserAccount.role))
    if filters.q:
        statement = statement.where(_search(filters.q))
    if filters.status is not None:
        statement = statement.where(UserAccount.is_active == (filters.status == "active"))
    if filters.role_id is not None:
        statement = statement.where(UserAccount.role_id == filters.role_id)
    statement = statement.order_by(
        folded(UserAccount.first_name), folded(UserAccount.last_name), UserAccount.id
    )
    return paginate(session, statement, params, request)


def get_user(session: Session, user_id: int) -> UserAccount:
    user = session.get(UserAccount, user_id, options=[joinedload(UserAccount.role)])
    if user is None:
        raise NotFound()
    return user


def list_logins(session: Session, user_id: int, params: PageParams, request: Request) -> Page:
    get_user(session, user_id)
    statement = (
        select(LoginEvent)
        .where(LoginEvent.user_id == user_id)
        .order_by(col(LoginEvent.created_at).desc(), col(LoginEvent.id).desc())
    )
    return paginate(session, statement, params, request)
