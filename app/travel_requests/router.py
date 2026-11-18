from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.travel_requests.schemas import (
    AdvisorOption,
    SummaryFilters,
    TravelRequestClose,
    TravelRequestCreate,
    TravelRequestDetail,
    TravelRequestFilters,
    TravelRequestListItem,
    TravelRequestReopen,
    TravelRequestSummary,
    TravelRequestUpdate,
)
from app.travel_requests.services import advisors, request_management, request_queries

router = APIRouter(prefix="/api", tags=["travel-requests"])

can_view = Depends(require_permission("travel_requests.view"))
can_manage = Depends(require_permission("travel_requests.manage"))
Manager = Annotated[UserAccount, can_manage]


@router.get("/travel-requests", dependencies=[can_view], responses=error_responses(401, 403))
def list_travel_requests(
    request: Request,
    session: SessionDep,
    filters: Annotated[TravelRequestFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[TravelRequestListItem]:
    return request_queries.list_requests(session, filters, params, request)


# Antes de /travel-requests/{request_id}: si no, "summary" y "advisors" se leerían como un id.
@router.get(
    "/travel-requests/summary", dependencies=[can_view], responses=error_responses(401, 403)
)
def travel_request_summary(
    session: SessionDep, filters: Annotated[SummaryFilters, Query()]
) -> TravelRequestSummary:
    return request_queries.request_summary(session, filters)


@router.get(
    "/travel-requests/advisors", dependencies=[can_view], responses=error_responses(401, 403)
)
def list_advisors(session: SessionDep) -> list[AdvisorOption]:
    return advisors.list_advisors(session)


@router.get(
    "/travel-requests/{request_id}",
    dependencies=[can_view],
    responses=error_responses(401, 403, 404),
)
def get_travel_request(request_id: RecordId, session: SessionDep) -> TravelRequestDetail:
    return request_queries.get_request(session, request_id)


@router.post(
    "/travel-requests", status_code=status.HTTP_201_CREATED, responses=error_responses(401, 403)
)
def create_travel_request(
    data: TravelRequestCreate, actor: Manager, session: SessionDep
) -> TravelRequestDetail:
    return request_management.create_request(session, actor, data)


@router.put(
    "/travel-requests/{request_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_travel_request(
    request_id: RecordId, data: TravelRequestUpdate, session: SessionDep
) -> TravelRequestDetail:
    return request_management.update_request(session, request_id, data)


@router.post("/travel-requests/{request_id}/close", responses=error_responses(401, 403, 404, 409))
def close_travel_request(
    request_id: RecordId, data: TravelRequestClose, actor: Manager, session: SessionDep
) -> TravelRequestDetail:
    return request_management.close_request(session, actor, request_id, data)


@router.post(
    "/travel-requests/{request_id}/reopen",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def reopen_travel_request(
    request_id: RecordId, data: TravelRequestReopen, session: SessionDep
) -> TravelRequestDetail:
    return request_management.reopen_request(session, request_id, data)
