"""Harden schema: exam publishing, session registrations, assignments, and audit logs

Revision ID: c59128f01a23
Revises: ea27ee5275cf
Create Date: 2026-11-14 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = 'c59128f01a23'
down_revision: Union[str, Sequence[str], None] = 'ea27ee5275cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)

    # 1. Update quizzes table with exam publishing fields if not present
    existing_quiz_cols = {col['name'] for col in insp.get_columns('quizzes')}
    if 'is_published' not in existing_quiz_cols:
        op.add_column('quizzes', sa.Column('is_published', sa.Boolean(), server_default='1', nullable=False))
    if 'is_exam' not in existing_quiz_cols:
        op.add_column('quizzes', sa.Column('is_exam', sa.Boolean(), server_default='0', nullable=False))
    if 'lock_back_navigation' not in existing_quiz_cols:
        op.add_column('quizzes', sa.Column('lock_back_navigation', sa.Boolean(), server_default='0', nullable=False))
    if 'due_date' not in existing_quiz_cols:
        op.add_column('quizzes', sa.Column('due_date', sa.DateTime(timezone=True), nullable=True))

    # 2. Update session_registrations table with attendance tracking columns
    existing_reg_cols = {col['name'] for col in insp.get_columns('session_registrations')}
    if 'joined_at' not in existing_reg_cols:
        op.add_column('session_registrations', sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True))
    if 'left_at' not in existing_reg_cols:
        op.add_column('session_registrations', sa.Column('left_at', sa.DateTime(timezone=True), nullable=True))

    # 3. Create assignments table if not exists
    existing_tables = set(insp.get_table_names())
    if 'assignments' not in existing_tables:
        op.create_table(
            'assignments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('sessions.id', ondelete='CASCADE'), index=True, nullable=False),
            sa.Column('instructor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('max_points', sa.Float(), server_default='100.0', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # 4. Create assignment_submissions table if not exists
    if 'assignment_submissions' not in existing_tables:
        op.create_table(
            'assignment_submissions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('assignments.id', ondelete='CASCADE'), index=True, nullable=False),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
            sa.Column('file_name', sa.String(length=255), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('file_size', sa.Integer(), server_default='0', nullable=False),
            sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('score', sa.Float(), nullable=True),
            sa.Column('feedback', sa.Text(), nullable=True),
        )

    # 5. Create chat_messages table if not exists
    if 'chat_messages' not in existing_tables:
        op.create_table(
            'chat_messages',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('conversation_id', sa.String(length=36), index=True, nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
            sa.Column('role', sa.String(length=20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('metadata_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True, nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    existing_tables = set(insp.get_table_names())

    if 'chat_messages' in existing_tables:
        op.drop_table('chat_messages')
    if 'assignment_submissions' in existing_tables:
        op.drop_table('assignment_submissions')
    if 'assignments' in existing_tables:
        op.drop_table('assignments')

    existing_reg_cols = {col['name'] for col in insp.get_columns('session_registrations')}
    if 'left_at' in existing_reg_cols:
        op.drop_column('session_registrations', 'left_at')
    if 'joined_at' in existing_reg_cols:
        op.drop_column('session_registrations', 'joined_at')

    existing_quiz_cols = {col['name'] for col in insp.get_columns('quizzes')}
    for col_name in ['due_date', 'lock_back_navigation', 'is_exam', 'is_published']:
        if col_name in existing_quiz_cols:
            op.drop_column('quizzes', col_name)
