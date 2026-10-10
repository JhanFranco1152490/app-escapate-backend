from sqlmodel import Session, select

from app.accounts.models import RolePermission


def permissions_of_role(session: Session, role_id: int) -> list[str]:
    statement = select(RolePermission.permission).where(RolePermission.role_id == role_id)
    return sorted(session.exec(statement).all())
