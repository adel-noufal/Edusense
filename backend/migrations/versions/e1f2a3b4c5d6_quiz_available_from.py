"""Add quizzes.available_from for the exam availability window (B13).

Stores UTC datetimes like due_date; NULL means "available immediately".
Reversible: downgrade drops the column (existing attempts are unaffected —
they reference quiz_id, not the window columns).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quizzes",
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quizzes", "available_from")
