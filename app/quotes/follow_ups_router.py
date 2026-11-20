from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.quotes.follow_up_schemas import (
    AlertSummary,
    FollowUpComplete,
    FollowUpCreate,
    FollowUpFilters,
    FollowUpOut,
)
from app.quotes.services import follow_ups

router = APIRouter(prefix="/api", tags=["follow-ups"])

Viewer = Annotated[UserAccount, Depends(require_permission("quotes.view"))]
Manager = Annotated[UserAccount, Depends(require_permission("quotes.manage"))]
_WRITE_ERRORS = error_responses(401, 403, 404, 409)


@router.get("/follow-ups", responses=error_responses(401, 403))
def list_follow_ups(
    request: Request,
    actor: Viewer,
    session: SessionDep,
    filters: Annotated[FollowUpFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[FollowUpOut]:
    return follow_ups.list_follow_ups(session, actor, filters, params, request)


@router.get("/follow-ups/alerts", responses=error_responses(401, 403))
def alert_summary(actor: Viewer, session: SessionDep, mine: bool = False) -> AlertSummary:
    return follow_ups.alert_summary(session, actor, mine)


@router.post(
    "/quotes/{quote_id}/follow-ups",
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def schedule_follow_up(
    quote_id: RecordId, data: FollowUpCreate, actor: Manager, session: SessionDep
) -> FollowUpOut:
    return follow_ups.schedule(session, actor, quote_id, data)


@router.post("/follow-ups/{follow_up_id}/complete", responses=_WRITE_ERRORS)
def complete_follow_up(
    follow_up_id: RecordId, data: FollowUpComplete, actor: Manager, session: SessionDep
) -> FollowUpOut:
    return follow_ups.complete(session, actor, follow_up_id, data)


@router.delete(
    "/follow-ups/{follow_up_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def remove_follow_up(follow_up_id: RecordId, actor: Manager, session: SessionDep) -> None:
    follow_ups.remove(session, follow_up_id)
