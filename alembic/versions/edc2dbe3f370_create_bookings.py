"""create bookings

Revision ID: edc2dbe3f370
Revises: ca6b916c1d81
Create Date: 2026-11-20 19:13:34.911119

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "edc2dbe3f370"
down_revision: Union[str, Sequence[str], None] = "ca6b916c1d81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "booking",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("sale_id", sa.BigInteger(), nullable=False),
        sa.Column("quote_item_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("service_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("confirmation_code", sa.String(length=60), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "service_type IN ('lodging', 'air', 'ground', 'tours', 'cruise', 'food', 'wholesaler', 'other')",
            name="ck_booking_type",
        ),
        sa.CheckConstraint(
            "status IN ('to_request', 'requested', 'confirmed', 'cancelled')",
            name="ck_booking_status",
        ),
        sa.ForeignKeyConstraint(["quote_item_id"], ["quote_item.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_id"], ["sale.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_id", "quote_item_id", name="uq_booking_quote_item"),
    )
    op.create_index(op.f("ix_booking_sale_id"), "booking", ["sale_id"], unique=False)
    op.create_index(op.f("ix_booking_status"), "booking", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_status"), table_name="booking")
    op.drop_index(op.f("ix_booking_sale_id"), table_name="booking")
    op.drop_table("booking")
