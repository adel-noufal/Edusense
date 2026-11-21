"""
Task 4 Verification: AI Lessons Tab failure
Root cause: LessonGenerator JSX referenced `publishModalQuiz` / `setPublishModalQuiz`
            without declaring them as state â€” causing ReferenceError on mount.
Verification:
  1. Backend /ai/generations?type=lesson returns 200 with proper shape
  2. Backend /ai/jobs/pending returns 200
  3. Backend /ai/job/{id} returns 404 for unknown job (not 500)
  4. The AITools.jsx LessonGenerator component no longer references publishModalQuiz
  5. QuizGenerator still has the PublishExamModal JSX (regression check)
"""
import os
import sys
import re

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.models import User

client = TestClient(app)


def get_auth_headers(role="instructor"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.role == role).first()
        if not user:
            user = db.query(User).first()
        token = create_access_token(subject=user.email, role=user.role)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def test_lessons_api_endpoints():
    print("\n--- 1. Test /ai/generations?type=lesson returns 200 with correct shape ---")
    headers = get_auth_headers()
    resp = client.get("/api/ai/generations?type=lesson", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    if data:
        item = data[0]
        for key in ("id", "type", "topic", "prompt", "created_at"):
            assert key in item, f"Missing key '{key}' in generation item"
    print(f"âœ“ /ai/generations?type=lesson returned {len(data)} items with correct shape")


def test_jobs_pending_endpoint():
    print("\n--- 2. Test /ai/jobs/pending returns 200 ---")
    headers = get_auth_headers()
    resp = client.get("/api/ai/jobs/pending", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    print(f"âœ“ /ai/jobs/pending returned {len(data)} pending jobs")


def test_job_poll_unknown_id():
    print("\n--- 3. Test /ai/job/{id} returns 404 for unknown job (not 500) ---")
    headers = get_auth_headers()
    resp = client.get("/api/ai/job/unknown-job-id-task4-test", headers=headers)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:200]}"
    print(f"âœ“ /ai/job/unknown returns 404 as expected: {resp.json().get('detail')}")


def test_lesson_generator_no_publish_modal_reference():
    print("\n--- 4. Verifying LessonGenerator JSX no longer references publishModalQuiz ---")
    jsx_path = os.path.join(
        os.path.dirname(BACKEND_DIR), "frontend", "src", "pages", "AITools.jsx"
    )
    with open(jsx_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract just LessonGenerator component
    lesson_start = content.find("export function LessonGenerator()")
    lesson_end = content.find("\nexport function FlashcardGenerator()")
    lesson_text = content[lesson_start:lesson_end]

    if "publishModalQuiz" in lesson_text:
        lines = lesson_text.split("\n")
        bad = [l for l in lines if "publishModalQuiz" in l]
        raise AssertionError(
            f"publishModalQuiz still referenced in LessonGenerator ({len(bad)} occurrences):\n"
            + "\n".join(bad)
        )
    print("âœ“ LessonGenerator contains no publishModalQuiz references (ReferenceError is gone)")


def test_quiz_generator_has_publish_modal():
    print("\n--- 5. Verifying QuizGenerator still has PublishExamModal (regression check) ---")
    jsx_path = os.path.join(
        os.path.dirname(BACKEND_DIR), "frontend", "src", "pages", "AITools.jsx"
    )
    with open(jsx_path, "r", encoding="utf-8") as f:
        content = f.read()

    quiz_start = content.find("export function QuizGenerator()")
    quiz_end = content.find("\nexport function VideoLibrary()")
    quiz_text = content[quiz_start:quiz_end]

    assert "publishModalQuiz" in quiz_text, "publishModalQuiz state missing from QuizGenerator"
    assert "setPublishModalQuiz" in quiz_text, "setPublishModalQuiz missing from QuizGenerator"
    assert "PublishExamModal" in quiz_text, "PublishExamModal JSX block missing from QuizGenerator"
    print("âœ“ QuizGenerator correctly declares publishModalQuiz state and renders PublishExamModal")


if __name__ == "__main__":
    test_lessons_api_endpoints()
    test_jobs_pending_endpoint()
    test_job_poll_unknown_id()
    test_lesson_generator_no_publish_modal_reference()
    test_quiz_generator_has_publish_modal()
    print("\nALL TASK 4 TESTS PASSED!")
