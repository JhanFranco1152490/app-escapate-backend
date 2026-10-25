from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.clients.schemas import (
    ClientCreate,
    ClientDetail,
    ClientFilters,
    ClientListItem,
    ClientUpdate,
)
from app.clients.services import client_management, client_queries
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/api", tags=["clients"])

can_view = Depends(require_permission("clients.view"))
can_manage = Depends(require_permission("clients.manage"))
Manager = Annotated[UserAccount, can_manage]


@router.get("/clients", dependencies=[can_view], responses=error_responses(401, 403))
def list_clients(
    request: Request,
    session: SessionDep,
    filters: Annotated[ClientFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[ClientListItem]:
    return client_queries.list_clients(session, filters, params, request)


@router.get(
    "/clients/{client_id}", dependencies=[can_view], responses=error_responses(401, 403, 404)
)
def get_client(client_id: RecordId, session: SessionDep) -> ClientDetail:
    return client_queries.get_client(session, client_id)


@router.post("/clients", status_code=status.HTTP_201_CREATED, responses=error_responses(401, 403))
def create_client(data: ClientCreate, actor: Manager, session: SessionDep) -> ClientDetail:
    return client_management.create_client(session, actor, data)


@router.put(
    "/clients/{client_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_client(client_id: RecordId, data: ClientUpdate, session: SessionDep) -> ClientDetail:
    return client_management.update_client(session, client_id, data)
