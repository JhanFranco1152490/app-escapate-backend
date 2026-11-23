"""create deletion record

Revision ID: 256333a3db9c
Revises: c5db46cd3fb7
Create Date: 2026-11-22 21:22:47.254437

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "256333a3db9c"
down_revision: Union[str, Sequence[str], None] = "c5db46cd3fb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deletion_record",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=17), nullable=False),
        sa.Column("record_id", sa.BigInteger(), nullable=False),
        sa.Column("sale_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("deleted_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('client_payment', 'actual_cost', 'operating_expense')",
            name="ck_deletion_kind",
        ),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deletion_record_deleted_at"), "deletion_record", ["deleted_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deletion_record_deleted_at"), table_name="deletion_record")
    op.drop_table("deletion_record")
