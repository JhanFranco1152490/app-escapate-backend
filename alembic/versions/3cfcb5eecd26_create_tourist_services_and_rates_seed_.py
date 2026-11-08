"""create tourist services and rates, seed their permissions

Revision ID: 3cfcb5eecd26
Revises: 8392bb82c09e
Create Date: 2026-11-07 19:12:02.811239

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3cfcb5eecd26"
down_revision: Union[str, Sequence[str], None] = "8392bb82c09e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["tourist_services.view", "tourist_services.manage"]
# Propuesta inicial para los roles sembrados; el administrador la ajusta desde el panel.
PROPOSED = {
    "Encargado de proveedores": ALL,
    "Asesor comercial": ["tourist_services.view"],
    "Operativo": ["tourist_services.view"],
}


def _grant(codes: list[str], role_filter: str, **params) -> None:
    op.execute(
        sa.text(
            "INSERT INTO role_permission (role_id, permission) "
            "SELECT id, permission FROM role, unnest(CAST(:codes AS varchar[])) AS permission "
            f"WHERE {role_filter}"
        ).bindparams(codes=codes, **params)
    )


def upgrade() -> None:
    op.create_table(
        "tourist_service",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("service_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("destination", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(attributes) = 'object'", name="ck_tourist_service_attributes"
        ),
        sa.CheckConstraint(
            "service_type IN ('lodging', 'air', 'ground', 'tours', 'cruise', 'food', 'wholesaler', 'other')",
            name="ck_tourist_service_type",
        ),
        sa.CheckConstraint(
            "(deactivated_at IS NULL) = (deactivated_by_id IS NULL)",
            name="ck_tourist_service_deactivated_by",
        ),
        sa.CheckConstraint(
            "is_active = (deactivated_at IS NULL)", name="ck_tourist_service_deactivated_at"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deactivated_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tourist_service_supplier_id"), "tourist_service", ["supplier_id"], unique=False
    )
    op.create_table(
        "service_rate",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("tourist_service_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("charge_unit", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("conditions", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "charge_unit IN ('per_night', 'per_person_per_night', 'per_person', 'per_trip', 'per_day', 'per_group', 'per_cabin', 'per_package', 'per_service')",
            name="ck_service_rate_charge_unit",
        ),
        sa.CheckConstraint(
            "currency <> 'COP' OR amount = trunc(amount)", name="ck_service_rate_whole_pesos"
        ),
        sa.CheckConstraint("currency IN ('COP', 'USD')", name="ck_service_rate_currency"),
        sa.CheckConstraint("amount > 0", name="ck_service_rate_amount"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from", name="ck_service_rate_validity"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tourist_service_id"], ["tourist_service.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_rate_tourist_service_id"),
        "service_rate",
        ["tourist_service_id"],
        unique=False,
    )

    _grant(ALL, "is_protected")
    # Aquí sí se busca por nombre: es la propuesta para los roles sembrados. Si alguno ya se
    # renombró desde el panel, no recibe nada y la migración sigue sin fallar.
    for role_name, codes in PROPOSED.items():
        _grant(codes, "name = :role_name", role_name=role_name)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permission WHERE permission = ANY(CAST(:codes AS varchar[]))"
        ).bindparams(codes=ALL)
    )

    op.drop_index(op.f("ix_service_rate_tourist_service_id"), table_name="service_rate")
    op.drop_table("service_rate")
    op.drop_index(op.f("ix_tourist_service_supplier_id"), table_name="tourist_service")
    op.drop_table("tourist_service")
