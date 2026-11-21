"""add quote revisions and item alternatives

Revision ID: 9d02608d2706
Revises: 0ca11311e209
Create Date: 2026-11-20 19:45:47.828786

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (autogenerate usa sus tipos)

# revision identifiers, used by Alembic.
revision: str = "9d02608d2706"
down_revision: Union[str, Sequence[str], None] = "0ca11311e209"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quote", sa.Column("previous_quote_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "quote", sa.Column("revision", sa.SmallInteger(), server_default="1", nullable=False)
    )
    op.create_foreign_key(
        "quote_previous_quote_id_fkey",
        "quote",
        "quote",
        ["previous_quote_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("quote_item", sa.Column("alternative_of_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "quote_item_alternative_of_id_fkey",
        "quote_item",
        "quote_item",
        ["alternative_of_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_column("quote_item", "alternative_of_id")
    op.drop_column("quote", "revision")
    op.drop_column("quote", "previous_quote_id")
