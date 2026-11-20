"""create quotes, seed their permissions

Revision ID: 5a3b2740bafd
Revises: d25dce943f91
Create Date: 2026-11-20 17:14:27.080972

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "5a3b2740bafd"
down_revision: Union[str, Sequence[str], None] = "d25dce943f91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["quotes.view", "quotes.manage"]
# Propuesta inicial para los roles sembrados; el administrador la ajusta desde el panel.
PROPOSED = {
    "Asesor comercial": ALL,
    "Operativo": ["quotes.view"],
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
        "quote",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("travel_request_id", sa.BigInteger(), nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("destination", sa.String(length=150), nullable=False),
        sa.Column("origin", sa.String(length=120), nullable=True),
        sa.Column("departure_date", sa.Date(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("adults", sa.SmallInteger(), nullable=False),
        sa.Column("minors", sa.SmallInteger(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("default_markup_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("deposit_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("balance_due_date", sa.Date(), nullable=True),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("policies", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status IN ('accepted', 'rejected')) = (decided_at IS NOT NULL)",
            name="ck_quote_decided_at",
        ),
        sa.CheckConstraint(
            "(status IN ('sent', 'accepted', 'rejected')) = (sent_at IS NOT NULL)",
            name="ck_quote_sent_at",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'sent', 'accepted', 'rejected')", name="ck_quote_status"
        ),
        sa.CheckConstraint("adults BETWEEN 1 AND 99", name="ck_quote_adults"),
        sa.CheckConstraint("default_markup_percent >= 0", name="ck_quote_default_markup"),
        sa.CheckConstraint(
            "deposit_percent IS NULL OR (deposit_percent > 0 AND deposit_percent <= 100)",
            name="ck_quote_deposit",
        ),
        sa.CheckConstraint("exchange_rate IS NULL OR exchange_rate > 0", name="ck_quote_exchange"),
        sa.CheckConstraint("minors BETWEEN 0 AND 99", name="ck_quote_minors"),
        sa.CheckConstraint(
            "return_date IS NULL OR departure_date IS NULL OR return_date >= departure_date",
            name="ck_quote_dates",
        ),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["travel_request_id"], ["travel_request.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quote_client_id"), "quote", ["client_id"], unique=False)
    op.create_index(op.f("ix_quote_status"), "quote", ["status"], unique=False)
    op.create_index(
        op.f("ix_quote_travel_request_id"), "quote", ["travel_request_id"], unique=False
    )
    op.create_table(
        "quote_item",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=False),
        sa.Column("service_type", sa.String(length=20), nullable=False),
        sa.Column("tourist_service_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
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
            name="ck_quote_item_charge_unit",
        ),
        sa.CheckConstraint(
            "currency <> 'COP' OR unit_cost = trunc(unit_cost)", name="ck_quote_item_whole_pesos"
        ),
        sa.CheckConstraint("currency IN ('COP', 'USD')", name="ck_quote_item_currency"),
        sa.CheckConstraint(
            "service_type IN ('lodging', 'air', 'ground', 'tours', 'cruise', 'food', 'wholesaler', 'other')",
            name="ck_quote_item_type",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_quote_item_dates",
        ),
        sa.CheckConstraint("markup_percent >= 0", name="ck_quote_item_markup"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_quote_item_quantity"),
        sa.CheckConstraint(
            "sale_price_override IS NULL OR sale_price_override >= 0",
            name="ck_quote_item_override",
        ),
        sa.CheckConstraint(
            "supplier_commission_percent IS NULL OR supplier_commission_percent BETWEEN 0 AND 100",
            name="ck_quote_item_commission",
        ),
        sa.CheckConstraint("unit_cost >= 0", name="ck_quote_item_unit_cost"),
        sa.ForeignKeyConstraint(["quote_id"], ["quote.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tourist_service_id"], ["tourist_service.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quote_item_quote_id"), "quote_item", ["quote_id"], unique=False)

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

    op.drop_index(op.f("ix_quote_item_quote_id"), table_name="quote_item")
    op.drop_table("quote_item")
    op.drop_index(op.f("ix_quote_travel_request_id"), table_name="quote")
    op.drop_index(op.f("ix_quote_status"), table_name="quote")
    op.drop_index(op.f("ix_quote_client_id"), table_name="quote")
    op.drop_table("quote")
