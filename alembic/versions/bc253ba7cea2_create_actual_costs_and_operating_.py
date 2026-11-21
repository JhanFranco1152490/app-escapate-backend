"""create actual costs and operating expenses, seed their permissions

Revision ID: bc253ba7cea2
Revises: edc2dbe3f370
Create Date: 2026-11-20 19:19:17.561304

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "bc253ba7cea2"
down_revision: Union[str, Sequence[str], None] = "edc2dbe3f370"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["finance.view", "finance.manage"]
# Propuesta inicial: el operativo lleva los pagos a proveedores y los gastos.
PROPOSED = {"Operativo": ALL}


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
        "operating_expense",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=12), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('rent', 'payroll', 'marketing', 'utilities', 'taxes', 'software', 'other')",
            name="ck_operating_expense_category",
        ),
        sa.CheckConstraint("amount > 0", name="ck_operating_expense_amount"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_operating_expense_spent_on"), "operating_expense", ["spent_on"], unique=False
    )
    op.create_table(
        "actual_cost",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("sale_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.String(length=150), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name="ck_actual_cost_amount"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_id"], ["sale.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_actual_cost_paid_on"), "actual_cost", ["paid_on"], unique=False)
    op.create_index(op.f("ix_actual_cost_sale_id"), "actual_cost", ["sale_id"], unique=False)

    _grant(ALL, "is_protected")
    for role_name, codes in PROPOSED.items():
        _grant(codes, "name = :role_name", role_name=role_name)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permission WHERE permission = ANY(CAST(:codes AS varchar[]))"
        ).bindparams(codes=ALL)
    )
    op.drop_index(op.f("ix_actual_cost_sale_id"), table_name="actual_cost")
    op.drop_index(op.f("ix_actual_cost_paid_on"), table_name="actual_cost")
    op.drop_table("actual_cost")
    op.drop_index(op.f("ix_operating_expense_spent_on"), table_name="operating_expense")
    op.drop_table("operating_expense")
