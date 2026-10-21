"""protect admin role, describe roles, seed role management permissions

Revision ID: 0fcb546ab89f
Revises: 060f18ee3a42
Create Date: 2026-10-20 23:18:51.926568

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0fcb546ab89f"
down_revision: Union[str, Sequence[str], None] = "060f18ee3a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DESCRIPTIONS = {
    "Administrador": "Acceso a todo el panel, incluida la gestión de usuarios y permisos.",
    "Asesor comercial": "Clientes, viajeros, solicitudes y borradores.",
    "Encargado de proveedores": "Proveedores, servicios y tarifas.",
    "Operativo": "Reservas, documentos y pagos posteriores a la venta.",
}


def upgrade() -> None:
    op.add_column("role", sa.Column("description", sa.String(length=200), nullable=True))
    op.add_column(
        "role",
        sa.Column("is_protected", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # Única vez que se busca el rol por nombre: desde aquí se reconoce por is_protected,
    # porque el nombre se puede editar.
    op.execute("UPDATE role SET is_protected = true WHERE name = 'Administrador'")
    describe = sa.text("UPDATE role SET description = :description WHERE name = :name")
    for name, description in DESCRIPTIONS.items():
        op.execute(describe.bindparams(name=name, description=description))

    op.drop_constraint("role_name_key", "role", type_="unique")
    op.create_index("uq_role_name_lower", "role", [sa.literal_column("lower(name)")], unique=True)

    op.execute(
        "INSERT INTO role_permission (role_id, permission) "
        "SELECT id, permission FROM role, unnest(ARRAY['roles.view', 'roles.manage']) "
        "AS permission WHERE is_protected"
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission IN ('roles.view', 'roles.manage')")

    op.drop_index("uq_role_name_lower", table_name="role")
    op.create_unique_constraint("role_name_key", "role", ["name"])

    op.drop_column("role", "is_protected")
    op.drop_column("role", "description")
