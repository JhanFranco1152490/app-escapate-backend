"""create suppliers, seed their permissions

Revision ID: 8392bb82c09e
Revises: c4a3b1c59b1a
Create Date: 2026-10-30 21:10:44.866550

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8392bb82c09e"
down_revision: Union[str, Sequence[str], None] = "c4a3b1c59b1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["suppliers.view", "suppliers.manage"]
# Propuesta inicial para los roles sembrados; el administrador la ajusta desde el panel.
PROPOSED = {
    "Encargado de proveedores": ALL,
    "Asesor comercial": ["suppliers.view"],
    "Operativo": ["suppliers.view"],
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
        "supplier",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("trade_name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("legal_name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=True),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column("document_number", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
        sa.Column("categories", sa.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("city", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True),
        sa.Column("coverage_zone", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=True),
        sa.Column("contact_name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
        sa.Column("contact_role", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True),
        sa.Column("contact_phone", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True),
        sa.Column("contact_email", sqlmodel.sql.sqltypes.AutoString(length=254), nullable=True),
        sa.Column("payment_terms", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("commission_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("agreement_valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "document_type IN ('NIT', 'CC', 'CE', 'FOREIGN')", name="ck_supplier_document_type"
        ),
        sa.CheckConstraint(
            "(document_type IS NULL) = (document_number IS NULL)",
            name="ck_supplier_document_pair",
        ),
        sa.CheckConstraint(
            "cardinality(categories) >= 1 AND categories <@ ARRAY['lodging', 'air', 'ground', "
            "'tours', 'cruise', 'food', 'wholesaler', 'other']::varchar[]",
            name="ck_supplier_categories",
        ),
        sa.CheckConstraint(
            "contact_phone IS NOT NULL OR contact_email IS NOT NULL", name="ck_supplier_contact"
        ),
        sa.CheckConstraint(
            "commission_rate BETWEEN 0 AND 100", name="ck_supplier_commission_rate"
        ),
        sa.CheckConstraint(
            "is_active = (deactivated_at IS NULL)", name="ck_supplier_deactivated_at"
        ),
        sa.CheckConstraint(
            "(deactivated_at IS NULL) = (deactivated_by_id IS NULL)",
            name="ck_supplier_deactivated_by",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deactivated_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_supplier_document",
        "supplier",
        ["document_type", "document_number"],
        unique=True,
        postgresql_where=sa.text("document_number IS NOT NULL"),
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

    op.drop_index("uq_supplier_document", table_name="supplier")
    op.drop_table("supplier")
