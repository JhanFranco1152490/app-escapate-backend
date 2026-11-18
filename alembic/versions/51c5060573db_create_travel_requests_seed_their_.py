"""create travel requests, seed their permissions

Revision ID: 51c5060573db
Revises: 3cfcb5eecd26
Create Date: 2026-11-13 17:40:18.001176

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "51c5060573db"
down_revision: Union[str, Sequence[str], None] = "3cfcb5eecd26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL = ["travel_requests.view", "travel_requests.manage"]
# Propuesta inicial para los roles sembrados; el administrador la ajusta desde el panel.
PROPOSED = {
    "Asesor comercial": ALL,
    "Operativo": ["travel_requests.view"],
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
        "travel_request",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("destination", sa.String(length=150), nullable=False),
        sa.Column("origin", sa.String(length=120), nullable=True),
        sa.Column("date_mode", sa.String(length=10), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("approx_nights", sa.SmallInteger(), nullable=True),
        sa.Column("adults", sa.SmallInteger(), nullable=False),
        sa.Column("minors", sa.SmallInteger(), nullable=False),
        sa.Column("budget_min", sa.BigInteger(), nullable=True),
        sa.Column("budget_max", sa.BigInteger(), nullable=True),
        sa.Column(
            "trip_types",
            postgresql.ARRAY(sa.String(length=20)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("accommodation_category", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("assigned_to_id", sa.BigInteger(), nullable=False),
        sa.Column("close_reason", sa.String(length=20), nullable=True),
        sa.Column("close_note", sa.String(length=300), nullable=True),
        sa.Column("closed_by_id", sa.BigInteger(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "date_mode IN ('exact', 'flexible')", name="ck_travel_request_date_mode"
        ),
        sa.CheckConstraint(
            "date_mode <> 'exact' OR (departure_date IS NOT NULL "
            "AND (return_date IS NULL OR return_date >= departure_date) "
            "AND window_start IS NULL AND window_end IS NULL AND approx_nights IS NULL)",
            name="ck_travel_request_exact_dates",
        ),
        sa.CheckConstraint(
            "date_mode <> 'flexible' OR (window_start IS NOT NULL AND window_end IS NOT NULL "
            "AND window_end >= window_start "
            "AND departure_date IS NULL AND return_date IS NULL)",
            name="ck_travel_request_flexible_dates",
        ),
        sa.CheckConstraint(
            "approx_nights BETWEEN 1 AND 365", name="ck_travel_request_approx_nights"
        ),
        sa.CheckConstraint("adults BETWEEN 1 AND 99", name="ck_travel_request_adults"),
        sa.CheckConstraint("minors BETWEEN 0 AND 99", name="ck_travel_request_minors"),
        sa.CheckConstraint(
            "(budget_min IS NULL OR budget_min > 0) AND (budget_max IS NULL OR budget_max > 0) "
            "AND (budget_min IS NULL OR budget_max IS NULL OR budget_max >= budget_min)",
            name="ck_travel_request_budget",
        ),
        sa.CheckConstraint(
            "trip_types <@ ARRAY['leisure', 'family', 'honeymoon', 'corporate', 'group', "
            "'adventure', 'other']::varchar[]",
            name="ck_travel_request_trip_types",
        ),
        sa.CheckConstraint(
            "accommodation_category IN ('budget', 'three_star', 'four_star', 'five_star')",
            name="ck_travel_request_accommodation_category",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'quoting', 'quoted', 'closed')", name="ck_travel_request_status"
        ),
        sa.CheckConstraint(
            "close_reason IN ('client_declined', 'no_response', 'bought_elsewhere', "
            "'duplicate', 'other')",
            name="ck_travel_request_close_reason",
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (close_reason IS NOT NULL) "
            "AND (status = 'closed') = (closed_by_id IS NOT NULL) "
            "AND (status = 'closed') = (closed_at IS NOT NULL)",
            name="ck_travel_request_closed",
        ),
        sa.CheckConstraint(
            "close_reason IS DISTINCT FROM 'other' OR close_note IS NOT NULL",
            name="ck_travel_request_close_note",
        ),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_travel_request_client_id"), "travel_request", ["client_id"], unique=False
    )
    op.create_index(
        op.f("ix_travel_request_assigned_to_id"),
        "travel_request",
        ["assigned_to_id"],
        unique=False,
    )
    op.create_index(op.f("ix_travel_request_status"), "travel_request", ["status"], unique=False)

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

    op.drop_index(op.f("ix_travel_request_status"), table_name="travel_request")
    op.drop_index(op.f("ix_travel_request_assigned_to_id"), table_name="travel_request")
    op.drop_index(op.f("ix_travel_request_client_id"), table_name="travel_request")
    op.drop_table("travel_request")
