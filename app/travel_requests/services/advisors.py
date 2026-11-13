"""Quién puede ser asesor responsable de una solicitud: una persona activa cuyo rol permite
gestionar solicitudes. El rol protegido tiene todos los permisos como filas, así que el
Administrador también aparece, sin un caso especial."""

from sqlalchemy import ColumnElement, and_
from sqlmodel import Session, col, select

from app.accounts.models import RolePermission, UserAccount

ADVISOR_PERMISSION = "travel_requests.manage"


def _can_be_advisor() -> ColumnElement[bool]:
    can_manage = select(RolePermission.role_id).where(
        RolePermission.permission == ADVISOR_PERMISSION
    )
    return and_(col(UserAccount.is_active), col(UserAccount.role_id).in_(can_manage))


def list_advisors(session: Session) -> list[UserAccount]:
    statement = (
        select(UserAccount)
        .where(_can_be_advisor())
        .order_by(UserAccount.first_name, UserAccount.last_name, UserAccount.id)
    )
    return list(session.exec(statement))


def is_eligible_advisor(session: Session, user_id: int) -> bool:
    statement = select(UserAccount.id).where(col(UserAccount.id) == user_id, _can_be_advisor())
    return session.exec(statement).first() is not None
