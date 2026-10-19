"""split user name, add phone, seed user management permissions

Revision ID: 060f18ee3a42
Revises: a3c91d2e7b10
Create Date: 2026-10-16 17:54:21.934637

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "060f18ee3a42"
down_revision: Union[str, Sequence[str], None] = "a3c91d2e7b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_account", sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(length=75))
    )
    op.add_column(
        "user_account", sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(length=75))
    )
    # full_name no separa nombres de apellidos: se parte por el primer espacio. Un nombre
    # compuesto ("María José Pérez") queda mal partido y se corrige desde la edición. Las
    # columnas nuevas miden la mitad que full_name, así que lo que no cabe se recorta en vez
    # de abortar la migración.
    op.execute(
        "UPDATE user_account SET "
        "first_name = left(split_part(full_name, ' ', 1), 75), "
        "last_name = left(CASE WHEN strpos(full_name, ' ') > 0 "
        "THEN substr(full_name, strpos(full_name, ' ') + 1) ELSE '' END, 75)"
    )
    op.alter_column("user_account", "first_name", nullable=False)
    op.alter_column("user_account", "last_name", nullable=False)
    op.drop_column("user_account", "full_name")

    op.add_column("user_account", sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=10)))
    op.create_unique_constraint("uq_user_account_phone", "user_account", ["phone"])

    # Para poder buscar personas por nombre sin que la tilde cambie el resultado.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.execute(
        "INSERT INTO role_permission (role_id, permission) "
        "SELECT id, permission FROM role, unnest(ARRAY['users.view', 'users.manage']) "
        "AS permission WHERE name = 'Administrador'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission IN ('users.view', 'users.manage')")

    op.drop_constraint("uq_user_account_phone", "user_account", type_="unique")
    op.drop_column("user_account", "phone")

    op.add_column(
        "user_account",
        sa.Column("full_name", sqlmodel.sql.sqltypes.AutoString(length=150)),
    )
    op.execute("UPDATE user_account SET full_name = trim(first_name || ' ' || last_name)")
    op.alter_column("user_account", "full_name", nullable=False)
    op.drop_column("user_account", "last_name")
    op.drop_column("user_account", "first_name")

    # La extensión unaccent no se borra: otra migración puede seguir usándola.
