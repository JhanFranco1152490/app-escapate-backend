"""add quality level to quote and package items

Revision ID: c5db46cd3fb7
Revises: e59167e1d210
Create Date: 2026-11-21 14:30:41.319264

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c5db46cd3fb7"
down_revision: Union[str, Sequence[str], None] = "e59167e1d210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEVELS = "quality_level IN ('economy', 'standard', 'superior', 'luxury')"


def upgrade() -> None:
    """Upgrade schema."""
    for table in ("quote_item", "package_item"):
        op.add_column(table, sa.Column("quality_level", sa.String(length=10), nullable=True))
        op.create_check_constraint(f"ck_{table}_quality_level", table, LEVELS)


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("package_item", "quote_item"):
        op.drop_constraint(f"ck_{table}_quality_level", table, type_="check")
        op.drop_column(table, "quality_level")
