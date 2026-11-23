"""Dejar constancia de un borrado y consultarla."""

from datetime import date

from fastapi import Request
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.audit.models import DeletionKind, DeletionRecord
from app.audit.schemas import DeletionFilters
from app.common.pagination import Page, PageParams, paginate


def record_deletion(
    session: Session,
    actor: UserAccount,
    *,
    kind: DeletionKind,
    record_id: int,
    amount: int,
    description: str,
    sale_id: int | None = None,
    occurred_on: date | None = None,
) -> None:
    """No hace `commit()`: va en la transacción del borrado, así que quedan los dos o ninguno."""
    session.add(
        DeletionRecord(
            kind=kind,
            record_id=record_id,
            sale_id=sale_id,
            description=description,
            amount=amount,
            occurred_on=occurred_on,
            deleted_by_id=actor.id,
        )
    )


def list_deletions(
    session: Session, filters: DeletionFilters, params: PageParams, request: Request
) -> Page:
    statement = select(DeletionRecord)
    if filters.kind is not None:
        statement = statement.where(col(DeletionRecord.kind) == filters.kind)
    statement = statement.options(joinedload(DeletionRecord.deleted_by)).order_by(
        col(DeletionRecord.deleted_at).desc(), col(DeletionRecord.id).desc()
    )
    return paginate(session, statement, params, request)
