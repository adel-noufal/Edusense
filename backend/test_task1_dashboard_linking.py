"""
Verification Test for Task 1:
1. Performance & Background Analysis Task Lifecycle
2. Session Linking & Unlinking for Lessons, Quizzes, and Generations
3. Persistence across session reloads
"""
import os
import sys
import json
import time

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.db.session import SessionLocal
from app.models.models import User, Session, AIGeneration, Quiz, EmotionLog
from app.api.sessions import _get_session_linked_content, list_sessions
from app.api.ai import _analytics_cache, _run_recommendations_bg, list_generations, poll_job
from app.schemas.schemas import SessionOut
from unittest.mock import MagicMock

def test_task1():
    db = SessionLocal()
    try:
        print("\n=== TASK 1 VERIFICATION TEST ===")
        
        # 1. Setup instructor user
        instructor = db.query(User).filter_by(role="instructor").first()
        if not instructor:
            instructor = User(name="Test Instructor", email="inst_task1@test.local", role="instructor", password_hash="hash")
            db.add(instructor)
            db.commit()
            db.refresh(instructor)
        print(f"1. Using instructor: {instructor.email} (id={instructor.id})")

        # 2. Setup an ended session
        session = db.query(Session).filter_by(instructor_id=instructor.id).first()
        if not session:
            from datetime import date, time as dt_time
            session = Session(
                instructor_id=instructor.id,
                title="Task 1 Test Session",
                description="Testing session linking and background analytics",
                date=date.today(),
                start_time=dt_time(10, 0),
                duration=60,
                status="ended",
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        else:
            session.status = "ended"
            db.commit()
        print(f"2. Using session: '{session.title}' (id={session.id}, status={session.status})")

        # 3. Create a test AIGeneration (Lesson)
        lesson_gen = AIGeneration(
            instructor_id=instructor.id,
            session_id=None,
            type="lesson",
            topic="Photosynthesis Deep Dive",
            prompt="Advanced biology lesson",
            data_json=json.dumps({"title": "Photosynthesis", "slides": []}),
        )
        db.add(lesson_gen)
        db.commit()
        db.refresh(lesson_gen)
        print(f"3. Created unlinked Lesson generation: id={lesson_gen.id}, topic='{lesson_gen.topic}'")

        # 4. Create a test Quiz
        quiz = Quiz(
            session_id=None,
            title="Cellular Energy Assessment",
            difficulty="Medium",
            questions_json=json.dumps([{"question": "What is ATP?", "answer": "Energy currency"}]),
        )
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        print(f"4. Created unlinked Quiz: id={quiz.id}, title='{quiz.title}'")

        # 5. Verify list_generations includes session_id and quizzes
        all_gens = list_generations(type=None, db=db, user=instructor)
        gen_ids = [g["id"] for g in all_gens if g["type"] == "lesson"]
        quiz_ids = [g["id"] for g in all_gens if g["type"] == "quiz"]
        assert lesson_gen.id in gen_ids, f"Lesson {lesson_gen.id} not found in list_generations"
        assert quiz.id in quiz_ids, f"Quiz {quiz.id} not found in list_generations"
        print(f"5. PASS: list_generations returns lessons AND quizzes with session_id field ({len(all_gens)} items)")

        # 6. Test linking lesson to session
        from app.api.sessions import link_generation_to_session, unlink_generation_from_session
        link_res = link_generation_to_session(session_id=session.id, gen_id=lesson_gen.id, type="lesson", db=db, user=instructor)
        print(f"6. Linked lesson response: {link_res}")
        db.refresh(lesson_gen)
        assert lesson_gen.session_id == session.id, "Lesson session_id not updated in DB"

        # 7. Test linking quiz to session
        link_quiz_res = link_generation_to_session(session_id=session.id, gen_id=quiz.id, type="quiz", db=db, user=instructor)
        print(f"7. Linked quiz response: {link_quiz_res}")
        db.refresh(quiz)
        assert quiz.session_id == session.id, "Quiz session_id not updated in DB"

        # 8. Verify persistence in SessionOut / _get_session_linked_content
        linked_items = _get_session_linked_content(session.id, db)
        linked_types = [item["type"] for item in linked_items]
        print(f"8. Linked content retrieved from DB for session {session.id}: {linked_items}")
        assert "lesson" in linked_types, "Linked lesson missing from session linked_content"
        assert "quiz" in linked_types, "Linked quiz missing from session linked_content"
        print("8. PASS: Both Lesson and Quiz are persistently linked and retrieved via _get_session_linked_content!")

        # 9. Verify SessionOut model validation includes linked_content
        from starlette.requests import Request
        fake_scope = {"type": "http", "method": "GET", "path": "/sessions", "headers": []}
        fake_req = Request(fake_scope)
        all_sessions = list_sessions(request=fake_req, db=db, user=instructor)
        curr_session_out = next((s for s in all_sessions if s.id == session.id), None)
        assert curr_session_out is not None, "Session not found in list_sessions"
        assert len(curr_session_out.linked_content) >= 2, f"Expected >= 2 linked items in SessionOut, got {curr_session_out.linked_content}"
        print(f"9. PASS: SessionOut includes {len(curr_session_out.linked_content)} linked items upon page reload!")

        # 10. Test unlinking lesson
        unlink_res = unlink_generation_from_session(session_id=session.id, gen_id=lesson_gen.id, type="lesson", db=db, user=instructor)
        print(f"10. Unlink lesson response: {unlink_res}")
        db.refresh(lesson_gen)
        assert lesson_gen.session_id is None, "Lesson session_id should be None after unlinking"

        # 11. Verify unlinked state in DB
        linked_after_unlink = _get_session_linked_content(session.id, db)
        assert not any(item["content_id"] == lesson_gen.id and item["type"] == "lesson" for item in linked_after_unlink)
        print("11. PASS: Lesson successfully unlinked and verified removed from session!")

        # 12. Test Background Analytics Job & Progress
        import uuid
        job_id = f"test-analytics-{uuid.uuid4()}"
        print(f"12. Running background analytics for session_id={session.id} (job_id={job_id})...")
        
        # Insert a dummy emotion log so telemetry has data
        dummy_log = EmotionLog(session_id=session.id, student_id=instructor.id, emotion="happy", confidence=0.92)
        db.add(dummy_log)
        db.commit()

        # Run background job synchronously to verify execution & progress
        _run_recommendations_bg(job_id, session.id, instructor.id)
        
        # Check job status via poll_job
        poll_res = poll_job(job_id, db=db, user=instructor)
        print(f"12. Polled analytics job result status: {poll_res.get('status')}")
        assert poll_res.get("status") == "done", f"Expected done status, got {poll_res}"
        res_data = poll_res.get("result")
        assert "recommendations" in res_data, "Missing recommendations in analytics result"
        assert "emotion_report" in res_data, "Missing emotion_report in analytics result"
        assert "engagement_report" in res_data, "Missing engagement_report in analytics result"
        print(f"12. PASS: Background analytics job completed with recommendations: {res_data['recommendations']['recommendations'][:2]}")

        # 13. Verify in-memory analytics caching
        cache_key = f"{instructor.id}:{session.id}"
        assert cache_key in _analytics_cache, "Analytics result was not stored in _analytics_cache"
        print(f"13. PASS: Analytics result successfully cached under key '{cache_key}' for instant load!")

        print("\nALL TASK 1 VERIFICATION CHECKS PASSED SUCCESSFULLY!\n")

    finally:
        db.close()

if __name__ == "__main__":
    test_task1()
