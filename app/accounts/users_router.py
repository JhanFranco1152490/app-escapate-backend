from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.accounts.schemas import (
    LoginEventItem,
    RecordId,
    UserCreate,
    UserDetail,
    UserFilters,
    UserInput,
    UserListItem,
    UserRoleInput,
    UserSaved,
)
from app.accounts.services import user_management, user_queries
from app.common.errors import error_responses
from app.common.pagination import Page, PageParams, page_params
from app.core.config import settings
from app.core.rate_limit import limiter

router = APIRouter(prefix="/api", tags=["users"])

can_view = Depends(require_permission("users.view"))
can_manage = Depends(require_permission("users.manage"))
Manager = Annotated[UserAccount, can_manage]


def _saved(result: user_management.SaveResult) -> UserSaved:
    return UserSaved(
        user=UserDetail.model_validate(result.user), invitation_sent=result.invitation_sent
    )


@router.get("/users", dependencies=[can_view], responses=error_responses(401, 403))
def list_users(
    request: Request,
    session: SessionDep,
    filters: Annotated[UserFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[UserListItem]:
    return user_queries.list_users(session, filters, params, request)


@router.get("/users/{user_id}", dependencies=[can_view], responses=error_responses(401, 403, 404))
def get_user(user_id: RecordId, session: SessionDep) -> UserDetail:
    return user_queries.get_user(session, user_id)


@router.get(
    "/users/{user_id}/logins",
    dependencies=[can_view],
    responses=error_responses(401, 403, 404),
)
def list_logins(
    user_id: RecordId,
    request: Request,
    session: SessionDep,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[LoginEventItem]:
    return user_queries.list_logins(session, user_id, params, request)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_manage],
    responses=error_responses(401, 403),
)
def create_user(data: UserCreate, session: SessionDep) -> UserSaved:
    return _saved(user_management.create_user(session, data))


@router.put(
    "/users/{user_id}", dependencies=[can_manage], responses=error_responses(401, 403, 404)
)
def update_user(user_id: RecordId, data: UserInput, session: SessionDep) -> UserSaved:
    return _saved(user_management.update_user(session, user_id, data))


@router.post("/users/{user_id}/deactivate", responses=error_responses(401, 403, 404, 409))
def deactivate_user(user_id: RecordId, actor: Manager, session: SessionDep) -> UserDetail:
    return user_management.deactivate_user(session, actor, user_id)


@router.post(
    "/users/{user_id}/activate",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404),
)
def activate_user(user_id: RecordId, session: SessionDep) -> UserDetail:
    return user_management.activate_user(session, user_id)


@router.post(
    "/users/{user_id}/invitation",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409, 429, 502),
)
@limiter.limit(lambda: settings.rate_user_invitation)
def resend_invitation(user_id: RecordId, request: Request, session: SessionDep) -> None:
    user_management.resend_invitation(session, user_id)


@router.delete(
    "/users/{user_id}/google", dependencies=[can_manage], responses=error_responses(401, 403, 404)
)
def unlink_google(user_id: RecordId, session: SessionDep) -> UserDetail:
    return user_management.unlink_google(session, user_id)


@router.put("/users/{user_id}/role", responses=error_responses(401, 403, 404, 409))
def change_role(
    user_id: RecordId, data: UserRoleInput, actor: Manager, session: SessionDep
) -> UserDetail:
    return user_management.change_role(session, actor, user_id, data.role_id)
