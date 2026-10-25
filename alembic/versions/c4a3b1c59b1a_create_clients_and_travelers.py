"""create clients and travelers, seed their permissions

Revision ID: c4a3b1c59b1a
Revises: 0fcb546ab89f
Create Date: 2026-10-25 14:17:17.350304

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a3b1c59b1a"
down_revision: Union[str, Sequence[str], None] = "0fcb546ab89f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["clients.view", "clients.manage", "travelers.view", "travelers.manage"]
# Propuesta inicial para los roles sembrados; el administrador la ajusta desde el panel.
PROPOSED = {
    "Asesor comercial": ALL,
    "Operativo": ["clients.view", "travelers.view"],
}


def _audit_columns() -> list:
    """Quién y cuándo autorizó el tratamiento de datos, quién registró y la versión."""
    return [
        sa.Column(
            "data_consent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("data_consent_by_id", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["data_consent_by_id"], ["user_account.id"], ondelete="RESTRICT"),
    ]


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
        "client",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("client_type", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(length=75), nullable=True),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(length=75), nullable=True),
        sa.Column("business_name", sqlmodel.sql.sqltypes.AutoString(length=150), nullable=True),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=True),
        sa.Column("document_number", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(length=254), nullable=True),
        sa.Column("city", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True),
        sa.Column("contact_source", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column(
            "contact_source_detail", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("client_type IN ('person', 'company')", name="ck_client_client_type"),
        sa.CheckConstraint(
            "document_type IN ('CC', 'CE', 'PPT', 'PA', 'NIT')", name="ck_client_document_type"
        ),
        sa.CheckConstraint(
            "(document_type IS NULL) = (document_number IS NULL)", name="ck_client_document_pair"
        ),
        sa.CheckConstraint(
            "client_type <> 'person' OR (first_name IS NOT NULL AND last_name IS NOT NULL "
            "AND business_name IS NULL "
            "AND (document_type IS NULL OR document_type IN ('CC', 'CE', 'PPT', 'PA')))",
            name="ck_client_person",
        ),
        sa.CheckConstraint(
            "client_type <> 'company' OR (business_name IS NOT NULL AND first_name IS NULL "
            "AND last_name IS NULL AND birth_date IS NULL "
            "AND (document_type IS NULL OR document_type = 'NIT'))",
            name="ck_client_company",
        ),
        sa.CheckConstraint(
            "contact_source IN "
            "('instagram', 'facebook', 'whatsapp', 'google', 'referral', 'walk_in', 'other')",
            name="ck_client_contact_source",
        ),
        sa.CheckConstraint(
            "contact_source <> 'other' OR contact_source_detail IS NOT NULL",
            name="ck_client_contact_source_detail",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_client_document",
        "client",
        ["document_type", "document_number"],
        unique=True,
        postgresql_where=sa.text("document_number IS NOT NULL"),
    )

    op.create_table(
        "traveler",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(length=75), nullable=False),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(length=75), nullable=False),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
        sa.Column("document_number", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("nationality", sa.String(length=2), nullable=False),
        sa.Column("reference_client_id", sa.BigInteger(), nullable=True),
        sa.Column("is_the_client", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(
            "document_type IN ('CC', 'CE', 'PPT', 'PA', 'TI', 'RC')",
            name="ck_traveler_document_type",
        ),
        sa.CheckConstraint(
            "NOT is_the_client OR reference_client_id IS NOT NULL",
            name="ck_traveler_is_the_client",
        ),
        sa.ForeignKeyConstraint(["reference_client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_traveler_reference_client_id"), "traveler", ["reference_client_id"], unique=False
    )
    op.create_index(
        "uq_traveler_document", "traveler", ["document_type", "document_number"], unique=True
    )
    op.create_index(
        "uq_traveler_is_the_client",
        "traveler",
        ["reference_client_id"],
        unique=True,
        postgresql_where=sa.text("is_the_client"),
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

    op.drop_index("uq_traveler_is_the_client", table_name="traveler")
    op.drop_index("uq_traveler_document", table_name="traveler")
    op.drop_index(op.f("ix_traveler_reference_client_id"), table_name="traveler")
    op.drop_table("traveler")
    op.drop_index("uq_client_document", table_name="client")
    op.drop_table("client")
