"""create tour packages

Revision ID: e59167e1d210
Revises: 9d02608d2706
Create Date: 2026-11-20 19:55:45.126969

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "e59167e1d210"
down_revision: Union[str, Sequence[str], None] = "9d02608d2706"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tour_package",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("destination", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("nights", sa.SmallInteger(), nullable=False),
        sa.Column("reference_travelers", sa.SmallInteger(), nullable=False),
        sa.Column("default_markup_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("default_markup_percent >= 0", name="ck_tour_package_markup"),
        sa.CheckConstraint(
            "exchange_rate IS NULL OR exchange_rate > 0", name="ck_tour_package_exchange"
        ),
        sa.CheckConstraint("nights BETWEEN 0 AND 365", name="ck_tour_package_nights"),
        sa.CheckConstraint(
            "reference_travelers BETWEEN 1 AND 99", name="ck_tour_package_travelers"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "package_item",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("package_id", sa.BigInteger(), nullable=False),
        sa.Column("service_type", sa.String(length=20), nullable=False),
        sa.Column("tourist_service_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("charge_unit", sa.String(length=30), nullable=True),
        sa.Column("is_optional", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("markup_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("sale_price_override", sa.BigInteger(), nullable=True),
        sa.Column("supplier_commission_percent", sa.Numeric(precision=5, scale=2), nullable=True),
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
            name="ck_package_item_charge_unit",
        ),
        sa.CheckConstraint(
            "currency <> 'COP' OR unit_cost = trunc(unit_cost)", name="ck_package_item_whole_pesos"
        ),
        sa.CheckConstraint("currency IN ('COP', 'USD')", name="ck_package_item_currency"),
        sa.CheckConstraint(
            "service_type IN ('lodging', 'air', 'ground', 'tours', 'cruise', 'food', 'wholesaler', 'other')",
            name="ck_package_item_type",
        ),
        sa.CheckConstraint("markup_percent >= 0", name="ck_package_item_markup"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_package_item_quantity"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_package_item_unit_cost"),
        sa.ForeignKeyConstraint(["package_id"], ["tour_package.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tourist_service_id"], ["tourist_service.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_package_item_package_id"), "package_item", ["package_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_package_item_package_id"), table_name="package_item")
    op.drop_table("package_item")
    op.drop_table("tour_package")
