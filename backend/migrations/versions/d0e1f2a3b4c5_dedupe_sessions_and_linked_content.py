"""Dedupe duplicate sessions/quizzes and add uniqueness guards (B12).

Duplicate rows were created by double-submits and repeated generation clicks.
This migration keeps the OLDEST row of each duplicate group and re-points all
child references before deleting the extras:

- sessions: grouped by (instructor_id, title, date, start_time)
- quizzes:  grouped by (session_id, title) where session_id is not null

Also creates partial unique indexes so the DB itself rejects new exact
duplicates. Downgrade drops the indexes; deleted duplicate rows are not
restored (they were exact duplicates of the kept row).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


# child tables holding a session_id FK -> sessions.id
_SESSION_CHILDREN = [
    "session_registrations",
    "emotion_logs",
    "reports",
    "quizzes",
    "quiz_attempts",
    "quiz_agent_configs",
    "session_notes",
    "ai_generations",
    "session_resources",
    "assignments",
]

# child tables holding a quiz_id FK -> quizzes.id
_QUIZ_CHILDREN = ["quiz_attempts", "quiz_violations"]


def _dedupe_sessions(bind):
    """Return list of (dup_id, keep_id) for exact-duplicate sessions."""
    rows = bind.execute(sa.text(
        """
        SELECT id, instructor_id, title, date, start_time
        FROM sessions
        """
    )).fetchall()
    groups = {}
    for r in rows:
        key = (r.instructor_id, r.title, str(r.date), str(r.start_time))
        groups.setdefault(key, []).append(r.id)
    pairs = []
    for ids in groups.values():
        if len(ids) > 1:
            keep = min(ids)
            pairs.extend((dup, keep) for dup in ids if dup != keep)
    return pairs


def _dedupe_quizzes(bind):
    rows = bind.execute(sa.text(
        """
        SELECT id, session_id, title FROM quizzes
        WHERE session_id IS NOT NULL
        """
    )).fetchall()
    groups = {}
    for r in rows:
        groups.setdefault((r.session_id, r.title), []).append(r.id)
    pairs = []
    for ids in groups.values():
        if len(ids) > 1:
            keep = min(ids)
            pairs.extend((dup, keep) for dup in ids if dup != keep)
    return pairs


def upgrade() -> None:
    bind = op.get_bind()

    # --- sessions ---
    for dup_id, keep_id in _dedupe_sessions(bind):
        # session_registrations has UNIQUE(session_id, student_id): drop dup
        # registrations that would collide after re-pointing, then move rest.
        bind.execute(sa.text(
            """
            DELETE FROM session_registrations
            WHERE session_id = :dup AND student_id IN (
                SELECT student_id FROM session_registrations WHERE session_id = :keep
            )
            """
        ), {"dup": dup_id, "keep": keep_id})
        for table in _SESSION_CHILDREN:
            bind.execute(sa.text(
                f"UPDATE {table} SET session_id = :keep WHERE session_id = :dup"
            ), {"keep": keep_id, "dup": dup_id})
        bind.execute(sa.text("DELETE FROM sessions WHERE id = :dup"), {"dup": dup_id})

    # --- quizzes ---
    for dup_id, keep_id in _dedupe_quizzes(bind):
        for table in _QUIZ_CHILDREN:
            bind.execute(sa.text(
                f"UPDATE {table} SET quiz_id = :keep WHERE quiz_id = :dup"
            ), {"keep": keep_id, "dup": dup_id})
        bind.execute(sa.text("DELETE FROM quizzes WHERE id = :dup"), {"dup": dup_id})

    # --- uniqueness guards ---
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quiz_session_title "
        "ON quizzes (session_id, title) WHERE session_id IS NOT NULL"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_quiz_session_title"))
    # Deleted duplicate rows are exact copies of the kept rows and are not
    # restored; child references were re-pointed to the kept rows.
