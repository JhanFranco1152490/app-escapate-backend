"""create travel request traveler

Revision ID: d25dce943f91
Revises: 51c5060573db
Create Date: 2026-11-18 17:33:22.220374

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d25dce943f91"
down_revision: Union[str, Sequence[str], None] = "51c5060573db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "travel_request_traveler",
        sa.Column("travel_request_id", sa.BigInteger(), nullable=False),
        sa.Column("traveler_id", sa.BigInteger(), nullable=False),
        sa.Column("added_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["added_by_id"], ["user_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["travel_request_id"], ["travel_request.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["traveler_id"], ["traveler.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("travel_request_id", "traveler_id"),
    )
    op.create_index(
        op.f("ix_travel_request_traveler_traveler_id"),
        "travel_request_traveler",
        ["traveler_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_travel_request_traveler_traveler_id"), table_name="travel_request_traveler"
    )
    op.drop_table("travel_request_traveler")
