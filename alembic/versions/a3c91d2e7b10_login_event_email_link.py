"""allow email_link as login event method

Revision ID: a3c91d2e7b10
Revises: f244bb9e4f47
Create Date: 2026-10-13 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c91d2e7b10"
down_revision: Union[str, Sequence[str], None] = "f244bb9e4f47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "ck_login_event_method"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "login_event", type_="check")
    op.create_check_constraint(
        CONSTRAINT, "login_event", "method IN ('document', 'google', 'email_link')"
    )


def downgrade() -> None:
    # El CHECK anterior no admite email_link: esos registros se pierden al bajar.
    op.execute("DELETE FROM login_event WHERE method = 'email_link'")
    op.drop_constraint(CONSTRAINT, "login_event", type_="check")
    op.create_check_constraint(CONSTRAINT, "login_event", "method IN ('document', 'google')")
