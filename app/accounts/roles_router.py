from fastapi import APIRouter, Depends, status

from app.accounts.dependencies import (
    CurrentUser,
    SessionDep,
    require_any_permission,
    require_permission,
)
from app.accounts.schemas import PermissionItem, RecordId, RoleDetail, RoleInput, RoleListItem
from app.accounts.services import role_management, role_queries
from app.common.errors import error_responses

router = APIRouter(prefix="/api", tags=["roles"])

# Quien cambia el rol de una persona necesita ver los roles y lo que autoriza cada uno, aunque
# no tenga acceso a la pantalla de roles. Solo leen: no dan nada que users.manage no permita.
can_list = Depends(require_any_permission("users.view", "roles.view"))
can_read = Depends(require_any_permission("roles.view", "users.manage"))
can_manage = Depends(require_permission("roles.manage"))


@router.get("/permissions", dependencies=[can_read], responses=error_responses(401, 403))
def list_permissions() -> list[PermissionItem]:
    return role_queries.permission_catalog()


@router.get("/roles", dependencies=[can_list], responses=error_responses(401, 403))
def list_roles(session: SessionDep) -> list[RoleListItem]:
    return role_queries.list_roles(session)


@router.get("/roles/{role_id}", dependencies=[can_read], responses=error_responses(401, 403, 404))
def get_role(role_id: RecordId, session: SessionDep) -> RoleDetail:
    return role_queries.get_role(session, role_id)


@router.post(
    "/roles",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_manage],
    responses=error_responses(401, 403),
)
def create_role(data: RoleInput, session: SessionDep) -> RoleDetail:
    return role_management.create_role(session, data)


@router.put(
    "/roles/{role_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_role(
    role_id: RecordId, data: RoleInput, actor: CurrentUser, session: SessionDep
) -> RoleDetail:
    return role_management.update_role(session, actor, role_id, data)


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def delete_role(role_id: RecordId, session: SessionDep) -> None:
    role_management.delete_role(session, role_id)
