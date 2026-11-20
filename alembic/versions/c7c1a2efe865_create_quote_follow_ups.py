"""create quote follow ups

Revision ID: c7c1a2efe865
Revises: 5a3b2740bafd
Create Date: 2026-11-20 18:09:47.906288

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "c7c1a2efe865"
down_revision: Union[str, Sequence[str], None] = "5a3b2740bafd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quote_follow_up",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("purpose", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'done') = (done_at IS NOT NULL)", name="ck_follow_up_done_at"
        ),
        sa.CheckConstraint(
            "channel IN ('call', 'whatsapp', 'email', 'meeting', 'other')",
            name="ck_follow_up_channel",
        ),
        sa.CheckConstraint("status IN ('pending', 'done')", name="ck_follow_up_status"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["done_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quote_id"], ["quote.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_quote_follow_up_due_date"), "quote_follow_up", ["due_date"], unique=False
    )
    op.create_index(
        op.f("ix_quote_follow_up_quote_id"), "quote_follow_up", ["quote_id"], unique=False
    )
    op.create_index(op.f("ix_quote_follow_up_status"), "quote_follow_up", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quote_follow_up_status"), table_name="quote_follow_up")
    op.drop_index(op.f("ix_quote_follow_up_quote_id"), table_name="quote_follow_up")
    op.drop_index(op.f("ix_quote_follow_up_due_date"), table_name="quote_follow_up")
    op.drop_table("quote_follow_up")
