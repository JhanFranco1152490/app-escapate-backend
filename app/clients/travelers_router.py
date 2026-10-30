from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.clients.schemas import (
    TravelerCreate,
    TravelerDetail,
    TravelerFilters,
    TravelerListItem,
    TravelerUpdate,
)
from app.clients.services import traveler_management, traveler_queries
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/api", tags=["travelers"])

can_view = Depends(require_permission("travelers.view"))
can_manage = Depends(require_permission("travelers.manage"))
Manager = Annotated[UserAccount, can_manage]


@router.get("/travelers", dependencies=[can_view], responses=error_responses(401, 403))
def list_travelers(
    request: Request,
    session: SessionDep,
    filters: Annotated[TravelerFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[TravelerListItem]:
    return traveler_queries.list_travelers(session, filters, params, request)


@router.get(
    "/travelers/{traveler_id}",
    dependencies=[can_view],
    responses=error_responses(401, 403, 404),
)
def get_traveler(traveler_id: RecordId, session: SessionDep) -> TravelerDetail:
    return traveler_queries.get_traveler(session, traveler_id)


@router.post(
    "/travelers", status_code=status.HTTP_201_CREATED, responses=error_responses(401, 403)
)
def create_traveler(data: TravelerCreate, actor: Manager, session: SessionDep) -> TravelerDetail:
    return traveler_management.create_traveler(session, actor, data)


@router.put(
    "/travelers/{traveler_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_traveler(
    traveler_id: RecordId, data: TravelerUpdate, session: SessionDep
) -> TravelerDetail:
    return traveler_management.update_traveler(session, traveler_id, data)
