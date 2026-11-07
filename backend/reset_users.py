"""
reset_users.py
--------------
Deletes ALL users from the database EXCEPT the two seed accounts:
  - instructor@edusense.local  (role: instructor)
  - student@edusense.local     (role: student)

All related rows (profiles, emotion_logs, session_registrations, etc.)
that are owned by deleted users are cascade-deleted via FK constraints.

Run from the backend/ directory:
    python reset_users.py
"""
import sys
import os

# Make sure the app package is on the path when run from backend/
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.db.session import engine, SessionLocal
from app.core.security import hash_password
from app.models.models import Base, User, Profile

SEED_USERS = [
    {
        "name": "Instructor",
        "email": "instructor@edusense.local",
        "password": "Password123",
        "role": "instructor",
    },
    {
        "name": "Student",
        "email": "student@edusense.local",
        "password": "Password123",
        "role": "student",
    },
]

SEED_EMAILS = {u["email"] for u in SEED_USERS}


def reset():
    db = SessionLocal()
    try:
        # 1. Find IDs of users that are NOT seed accounts
        non_seed_users = db.query(User).filter(User.email.notin_(SEED_EMAILS)).all()
        non_seed_ids = [u.id for u in non_seed_users]

        if not non_seed_ids:
            print("No extra users found — database is already clean.")
        else:
            print(f"Deleting {len(non_seed_ids)} non-seed user(s): {[u.email for u in non_seed_users]}")

            # Delete dependent rows in correct FK order
            # Sessions owned by these instructors must be deleted first,
            # along with all their children.
            id_list = tuple(non_seed_ids) if len(non_seed_ids) > 1 else f"({non_seed_ids[0]})"
            with engine.begin() as conn:
                # --- session children ---
                conn.execute(text(f"DELETE FROM emotion_logs           WHERE session_id IN (SELECT id FROM sessions WHERE instructor_id IN {id_list})"))
                conn.execute(text(f"DELETE FROM session_registrations  WHERE session_id IN (SELECT id FROM sessions WHERE instructor_id IN {id_list})"))
                conn.execute(text(f"DELETE FROM session_notes          WHERE session_id IN (SELECT id FROM sessions WHERE instructor_id IN {id_list})"))
                conn.execute(text(f"DELETE FROM quizzes                WHERE session_id IN (SELECT id FROM sessions WHERE instructor_id IN {id_list})"))
                conn.execute(text(f"DELETE FROM reports                WHERE session_id IN (SELECT id FROM sessions WHERE instructor_id IN {id_list})"))
                # --- sessions themselves ---
                conn.execute(text(f"DELETE FROM sessions               WHERE instructor_id IN {id_list}"))
                # --- user-level children ---
                conn.execute(text(f"DELETE FROM feedback               WHERE user_id      IN {id_list}"))
                conn.execute(text(f"DELETE FROM session_notes          WHERE student_id   IN {id_list}"))
                conn.execute(text(f"DELETE FROM emotion_logs           WHERE student_id   IN {id_list}"))
                conn.execute(text(f"DELETE FROM session_registrations  WHERE student_id   IN {id_list}"))
                conn.execute(text(f"DELETE FROM ai_generations         WHERE instructor_id IN {id_list}"))
                conn.execute(text(f"DELETE FROM video_projects         WHERE instructor_id IN {id_list}"))
                conn.execute(text(f"DELETE FROM profiles               WHERE user_id      IN {id_list}"))
                conn.execute(text(f"DELETE FROM users                  WHERE id           IN {id_list}"))

            print("Deleted successfully.")

        # 2. Ensure seed users exist (upsert)
        print("\nEnsuring seed users exist...")
        for seed in SEED_USERS:
            existing = db.query(User).filter(User.email == seed["email"]).first()
            if existing:
                # Reset password in case it was changed
                existing.name = seed["name"]
                existing.password_hash = hash_password(seed["password"])
                existing.role = seed["role"]
                db.commit()
                db.refresh(existing)
                uid = existing.id
                print(f"  [OK] {seed['email']} already exists (id={uid}) - password reset.")
            else:
                user = User(
                    name=seed["name"],
                    email=seed["email"],
                    role=seed["role"],
                    password_hash=hash_password(seed["password"]),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                uid = user.id
                print(f"  [OK] Created {seed['email']} (id={uid}).")

            # Ensure profile row exists
            profile = db.query(Profile).filter(Profile.user_id == uid).first()
            if not profile:
                db.add(Profile(user_id=uid))
                db.commit()
                print(f"    Profile created for user {uid}.")

        print("\n[DONE] Database now contains only seed users.")
        print("   instructor@edusense.local / Password123")
        print("   student@edusense.local    / Password123")

    finally:
        db.close()


if __name__ == "__main__":
    reset()
