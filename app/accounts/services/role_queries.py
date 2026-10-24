"""Lecturas de roles: lista con su número de personas, detalle y catálogo de permisos."""

from sqlalchemy import func, not_
from sqlmodel import Session, select

from app.accounts.models import Role, RolePermission, UserAccount
from app.accounts.permissions import PERMISSIONS
from app.accounts.schemas import PermissionItem, RoleDetail, RoleListItem
from app.common.errors import NotFound
from app.common.search import folded


def _roles_with_user_counts():
    user_count = func.count(UserAccount.id)
    inactive_user_count = func.count(UserAccount.id).filter(not_(UserAccount.is_active))
    return (
        select(Role, user_count, inactive_user_count)
        .outerjoin(UserAccount, UserAccount.role_id == Role.id)
        .group_by(Role.id)
    )


def _list_item(role: Role, user_count: int, inactive_user_count: int) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_protected": role.is_protected,
        "user_count": user_count,
        "inactive_user_count": inactive_user_count,
    }


def list_roles(session: Session) -> list[RoleListItem]:
    rows = session.exec(_roles_with_user_counts().order_by(folded(Role.name), Role.id)).all()
    return [RoleListItem(**_list_item(*row)) for row in rows]


def registered_permissions_of(session: Session, role_id: int) -> frozenset[str]:
    """Los permisos del rol que siguen en el registro. Una fila de un código retirado no
    autoriza nada (`require_permission` solo acepta códigos registrados), así que no cuenta."""
    statement = select(RolePermission.permission).where(RolePermission.role_id == role_id)
    return frozenset(code for code in session.exec(statement) if code in PERMISSIONS)


def get_role(session: Session, role_id: int) -> RoleDetail:
    row = session.exec(_roles_with_user_counts().where(Role.id == role_id)).first()
    if row is None:
        raise NotFound()
    role = row[0]
    return RoleDetail(
        **_list_item(*row),
        permissions=sorted(registered_permissions_of(session, role_id)),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def permission_catalog() -> list[PermissionItem]:
    return [
        PermissionItem(
            code=code,
            section=info.section,
            group=info.group,
            label=info.label,
            description=info.description,
            requires=list(info.requires),
            help=info.help,
        )
        for code, info in PERMISSIONS.items()
    ]
