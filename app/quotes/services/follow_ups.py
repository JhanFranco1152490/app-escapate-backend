"""Seguimientos comerciales: programar, registrar el resultado, listar y contar alertas."""

from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import ColumnElement, and_, func
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.common.errors import ApiError, NotFound
from app.common.pagination import Page, PageParams, paginate
from app.quotes.follow_up_models import AlertColor, FollowUpStatus, QuoteFollowUp
from app.quotes.follow_up_schemas import (
    AlertSummary,
    FollowUpComplete,
    FollowUpCreate,
    FollowUpFilters,
)
from app.quotes.models import Quote, QuoteStatus


class FollowUpAlreadyDone(ApiError):
    status_code, code = 409, "follow_up_done"
    detail = "Este seguimiento ya se registró."


class QuoteClosedForFollowUps(ApiError):
    status_code, code = 409, "quote_closed"
    detail = "La cotización ya fue aceptada o rechazada: no necesita seguimiento."


_DUE = col(QuoteFollowUp.due_date)


def _alert_condition(alert: AlertColor) -> ColumnElement[bool]:
    day = today()
    if alert == AlertColor.RED:
        return _DUE < day
    if alert == AlertColor.YELLOW:
        return and_(_DUE >= day, _DUE <= day + timedelta(days=1))
    return _DUE > day + timedelta(days=1)


def _with_quote():
    return [
        joinedload(QuoteFollowUp.quote).joinedload(Quote.client),
        joinedload(QuoteFollowUp.created_by),
        joinedload(QuoteFollowUp.done_by),
    ]


def _get(session: Session, follow_up_id: int) -> QuoteFollowUp:
    follow_up = session.get(QuoteFollowUp, follow_up_id, options=_with_quote())
    if follow_up is None:
        raise NotFound()
    return follow_up


def list_follow_ups(
    session: Session,
    actor: UserAccount,
    filters: FollowUpFilters,
    params: PageParams,
    request: Request,
) -> Page:
    statement = select(QuoteFollowUp)
    if filters.status is not None:
        statement = statement.where(col(QuoteFollowUp.status) == filters.status)
    if filters.alert is not None:
        statement = statement.where(
            col(QuoteFollowUp.status) == FollowUpStatus.PENDING,
            _alert_condition(filters.alert),
        )
    if filters.quote_id is not None:
        statement = statement.where(col(QuoteFollowUp.quote_id) == filters.quote_id)
    if filters.mine:
        statement = statement.where(col(QuoteFollowUp.created_by_id) == actor.id)
    # Lo más urgente primero; los ya registrados, del más reciente al más viejo.
    order = (
        (col(QuoteFollowUp.done_at).desc(),) if filters.status == FollowUpStatus.DONE else (_DUE,)
    )
    statement = statement.options(*_with_quote()).order_by(*order, col(QuoteFollowUp.id))
    return paginate(session, statement, params, request)


def alert_summary(session: Session, actor: UserAccount, mine: bool) -> AlertSummary:
    pending = col(QuoteFollowUp.status) == FollowUpStatus.PENDING
    conditions = [pending]
    if mine:
        conditions.append(col(QuoteFollowUp.created_by_id) == actor.id)
    row = session.exec(
        select(
            *(
                func.count().filter(_alert_condition(color)).label(color.value)
                for color in AlertColor
            )
        ).where(*conditions)
    ).one()
    return AlertSummary(red=row.red, yellow=row.yellow, green=row.green)


def _schedule(session: Session, actor: UserAccount, quote_id: int, due_date, channel, purpose):
    follow_up = QuoteFollowUp(
        quote_id=quote_id,
        due_date=due_date,
        channel=channel,
        purpose=purpose,
        created_by_id=actor.id,
    )
    session.add(follow_up)
    return follow_up


def schedule(
    session: Session, actor: UserAccount, quote_id: int, data: FollowUpCreate
) -> QuoteFollowUp:
    quote = session.get(Quote, quote_id)
    if quote is None:
        raise NotFound()
    if quote.status in (QuoteStatus.ACCEPTED, QuoteStatus.REJECTED):
        raise QuoteClosedForFollowUps()
    follow_up = _schedule(session, actor, quote.id, data.due_date, data.channel, data.purpose)
    session.commit()
    return _get(session, follow_up.id)


def complete(
    session: Session, actor: UserAccount, follow_up_id: int, data: FollowUpComplete
) -> QuoteFollowUp:
    follow_up = session.exec(
        select(QuoteFollowUp).where(QuoteFollowUp.id == follow_up_id).with_for_update()
    ).first()
    if follow_up is None:
        raise NotFound()
    if follow_up.status == FollowUpStatus.DONE:
        raise FollowUpAlreadyDone()
    follow_up.status = FollowUpStatus.DONE
    follow_up.outcome = data.outcome
    follow_up.done_at = datetime.now(timezone.utc)
    follow_up.done_by_id = actor.id
    if data.next_due_date is not None:
        _schedule(
            session,
            actor,
            follow_up.quote_id,
            data.next_due_date,
            follow_up.channel,
            data.next_purpose or follow_up.purpose,
        )
    session.commit()
    return _get(session, follow_up.id)


def remove(session: Session, follow_up_id: int) -> None:
    follow_up = session.get(QuoteFollowUp, follow_up_id)
    if follow_up is None:
        raise NotFound()
    if follow_up.status == FollowUpStatus.DONE:
        raise FollowUpAlreadyDone()
    session.delete(follow_up)
    session.commit()
