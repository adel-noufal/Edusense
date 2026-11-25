"""Optional session duration + quiz reveal_answers policy

Revision ID: a1b2c3d4e5f6
Revises: c59128f01a23
Create Date: 2026-12-20 00:00:00.000000

- sessions.duration becomes nullable (NULL = no time limit)
- quizzes.reveal_answers added (instructor policy for post-submit answer review)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c59128f01a23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)

    # 1. quizzes.reveal_answers
    quiz_cols = {c['name'] for c in insp.get_columns('quizzes')}
    if 'reveal_answers' not in quiz_cols:
        op.add_column('quizzes', sa.Column('reveal_answers', sa.Boolean(),
                                           server_default=sa.true(), nullable=False))

    # 2. sessions.duration -> nullable (no time limit)
    sess_cols = {c['name']: c for c in insp.get_columns('sessions')}
    dur = sess_cols.get('duration')
    if dur is not None and not dur['nullable']:
        if conn.dialect.name == 'postgresql':
            op.alter_column('sessions', 'duration',
                            existing_type=sa.Integer(), nullable=True)
        else:
            # SQLite: batch mode recreates the table without NOT NULL
            with op.batch_alter_table('sessions') as batch_op:
                batch_op.alter_column('duration', existing_type=sa.Integer(),
                                      nullable=True)


def downgrade() -> None:
    conn = op.get_bind()
    # Restore NOT NULL only if no NULL durations exist
    null_count = conn.execute(sa.text(
        "SELECT COUNT(*) FROM sessions WHERE duration IS NULL")).scalar()
    if not null_count:
        if conn.dialect.name == 'postgresql':
            op.alter_column('sessions', 'duration',
                            existing_type=sa.Integer(), nullable=False)
        else:
            with op.batch_alter_table('sessions') as batch_op:
                batch_op.alter_column('duration', existing_type=sa.Integer(),
                                      nullable=False)
    op.drop_column('quizzes', 'reveal_answers')
