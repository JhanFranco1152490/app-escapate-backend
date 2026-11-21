"""create sales and client payments, seed their permissions

Revision ID: ca6b916c1d81
Revises: c7c1a2efe865
Create Date: 2026-11-20 18:18:26.007986

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "ca6b916c1d81"
down_revision: Union[str, Sequence[str], None] = "c7c1a2efe865"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["sales.view", "sales.manage"]
# Propuesta inicial: el asesor registra la venta y el operativo los pagos posteriores.
PROPOSED = {"Asesor comercial": ALL, "Operativo": ALL}


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
        "sale",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("destination", sa.String(length=150), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("adults", sa.Integer(), nullable=False),
        sa.Column("minors", sa.Integer(), nullable=False),
        sa.Column("total_price", sa.BigInteger(), nullable=False),
        sa.Column("total_cost", sa.BigInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("total_cost >= 0", name="ck_sale_total_cost"),
        sa.CheckConstraint("total_price > 0", name="ck_sale_total_price"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quote_id"], ["quote.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id"),
    )
    op.create_index(op.f("ix_sale_client_id"), "sale", ["client_id"], unique=False)
    op.create_table(
        "client_payment",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("sale_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "method IN ('transfer', 'cash', 'card', 'other')", name="ck_client_payment_method"
        ),
        sa.CheckConstraint("amount > 0", name="ck_client_payment_amount"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_id"], ["sale.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_client_payment_sale_id"), "client_payment", ["sale_id"], unique=False)

    _grant(ALL, "is_protected")
    for role_name, codes in PROPOSED.items():
        _grant(codes, "name = :role_name", role_name=role_name)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permission WHERE permission = ANY(CAST(:codes AS varchar[]))"
        ).bindparams(codes=ALL)
    )
    op.drop_index(op.f("ix_client_payment_sale_id"), table_name="client_payment")
    op.drop_table("client_payment")
    op.drop_index(op.f("ix_sale_client_id"), table_name="sale")
    op.drop_table("sale")
