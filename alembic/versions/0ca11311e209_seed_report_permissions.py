"""seed report permissions

Revision ID: 0ca11311e209
Revises: bc253ba7cea2
Create Date: 2026-11-20 19:30:09.423911

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "0ca11311e209"
down_revision: Union[str, Sequence[str], None] = "bc253ba7cea2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALL = ["reports.view"]
# Propuesta inicial: el dashboard y los reportes los ven todos los roles de la operación.
PROPOSED = ["Asesor comercial", "Operativo"]


def _grant(role_filter: str, **params) -> None:
    op.execute(
        sa.text(
            "INSERT INTO role_permission (role_id, permission) "
            "SELECT id, permission FROM role, unnest(CAST(:codes AS varchar[])) AS permission "
            f"WHERE {role_filter}"
        ).bindparams(codes=ALL, **params)
    )


def upgrade() -> None:
    _grant("is_protected")
    for role_name in PROPOSED:
        _grant("name = :role_name", role_name=role_name)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permission WHERE permission = ANY(CAST(:codes AS varchar[]))"
        ).bindparams(codes=ALL)
    )
