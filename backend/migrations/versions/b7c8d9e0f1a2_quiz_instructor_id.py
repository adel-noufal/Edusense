"""Quiz instructor_id for exam visibility scoping

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-12-21 00:00:00.000000

- quizzes.instructor_id (nullable FK -> users.id) records the owning
  instructor so session-less exams can be scoped to "all my students".
- Backfills instructor_id from the owning session where possible.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    quiz_cols = {c['name'] for c in insp.get_columns('quizzes')}
    if 'instructor_id' not in quiz_cols:
        # Plain column + index: SQLite cannot add FK constraints via ALTER.
        # The ORM-level ForeignKey still applies on Postgres-created schemas;
        # referential integrity is enforced by application code here.
        op.add_column('quizzes', sa.Column('instructor_id', sa.Integer(), nullable=True))
        op.create_index('ix_quizzes_instructor_id', 'quizzes', ['instructor_id'])

    # Backfill from the linked session's instructor (best effort, idempotent)
    try:
        conn.execute(sa.text(
            "UPDATE quizzes SET instructor_id = ("
            "  SELECT instructor_id FROM sessions WHERE sessions.id = quizzes.session_id"
            ") WHERE instructor_id IS NULL AND session_id IS NOT NULL"
        ))
    except Exception:
        pass


def downgrade() -> None:
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    quiz_cols = {c['name'] for c in insp.get_columns('quizzes')}
    if 'instructor_id' in quiz_cols:
        try:
            op.drop_index('ix_quizzes_instructor_id', table_name='quizzes')
        except Exception:
            pass
        op.drop_column('quizzes', 'instructor_id')
