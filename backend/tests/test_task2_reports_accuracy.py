import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from app.db.session import SessionLocal
from app.models.models import (
    AuditLog,
    EmotionLog,
    Session as ClassSession,
    SessionRegistration,
    User,
)
from app.services.attendance_service import (
    calculate_session_attended_duration,
    calculate_student_attended_duration,
)
from app.api.reports import _session_report_payload, _student_report_payload
from app.agents.base import AgentResult


def p(msg):
    print(msg, flush=True)


def test_task2_reports_accuracy():
    p("=== TASK 2 VERIFICATION TEST: REPORTS ATTENDED DURATION ACCURACY ===")
    db = SessionLocal()
    try:
        # 1. Setup instructor and student
        instructor = db.query(User).filter_by(role="instructor").first()
        student = db.query(User).filter_by(role="student").first()
        assert instructor, "No instructor user found"
        assert student, "No student user found"
        p(f"1. Instructor: {instructor.email} (id={instructor.id}), Student: {student.email} (id={student.id})")

        # 2. Create a session with scheduled duration of 60 minutes
        test_session = ClassSession(
            instructor_id=instructor.id,
            title="Task 2 Duration Accuracy Test Session",
            description="Testing accurate attended duration calculation vs scheduled duration",
            date=date.today(),
            start_time=time(14, 0),
            duration=60,  # Scheduled duration = 60 minutes
            status="ended",
        )
        db.add(test_session)
        db.commit()
        db.refresh(test_session)
        p(f"2. Created session id={test_session.id} with scheduled duration = {test_session.duration}m")

        # 3. Initially without attendance, duration should be 0, scheduled_duration should be 60
        dur_initial = calculate_session_attended_duration(db, test_session.id)
        assert dur_initial == 0, f"Expected 0 attended duration without attendees, got {dur_initial}"
        payload_initial = _session_report_payload(db, test_session)
        assert payload_initial["duration"] == 0, f"Expected 0 duration, got {payload_initial['duration']}"
        assert payload_initial["scheduled_duration"] == 60, f"Expected 60 scheduled_duration, got {payload_initial['scheduled_duration']}"
        p("3. PASS: Unattended session report shows attended duration = 0m, scheduled_duration = 60m")

        # 4. Enroll student and simulate real 2-minute attendance window
        # Joined at T0, left at T0 + 2 minutes (120 seconds)
        t0 = datetime.now(timezone.utc) - timedelta(hours=1)
        t_leave = t0 + timedelta(minutes=2)

        reg = SessionRegistration(
            session_id=test_session.id,
            student_id=student.id,
            attended=True,
            joined_at=t0,
            left_at=t_leave,
        )
        db.add(reg)

        # Also add EmotionLog heartbeats spanning the exact 2 minutes
        log1 = EmotionLog(
            session_id=test_session.id,
            student_id=student.id,
            emotion="happy",
            confidence=0.92,
            timestamp=t0,
        )
        log2 = EmotionLog(
            session_id=test_session.id,
            student_id=student.id,
            emotion="neutral",
            confidence=0.88,
            timestamp=t0 + timedelta(seconds=60),
        )
        log3 = EmotionLog(
            session_id=test_session.id,
            student_id=student.id,
            emotion="happy",
            confidence=0.95,
            timestamp=t_leave,
        )
        db.add_all([log1, log2, log3])
        db.commit()
        p(f"4. Created SessionRegistration and 3 EmotionLog heartbeats from {t0.isoformat()} to {t_leave.isoformat()} (delta = 2m)")

        # 5. Verify calculate_student_attended_duration returns 2 minutes (NOT 60m)
        student_dur = calculate_student_attended_duration(db, test_session.id, student.id)
        p(f"5. Calculated student attended duration: {student_dur} minutes")
        assert student_dur == 2, f"Expected student duration to be 2 minutes, got {student_dur}"
        p("5. PASS: Student attended duration accurately calculated as 2m!")

        # 6. Verify calculate_session_attended_duration returns 2 minutes (NOT 60m)
        session_dur = calculate_session_attended_duration(db, test_session.id)
        p(f"6. Calculated session attended duration: {session_dur} minutes")
        assert session_dur == 2, f"Expected session duration to be 2 minutes, got {session_dur}"
        p("6. PASS: Session attended duration accurately calculated as 2m!")

        # 7. Verify _session_report_payload returns duration=2 and scheduled_duration=60
        session_report = _session_report_payload(db, test_session)
        p(f"7. Session report payload: duration={session_report['duration']}m, scheduled_duration={session_report['scheduled_duration']}m")
        assert session_report["duration"] == 2, f"Expected report duration = 2m, got {session_report['duration']}"
        assert session_report["attended_duration"] == 2, f"Expected attended_duration = 2m, got {session_report['attended_duration']}"
        assert session_report["scheduled_duration"] == 60, f"Expected scheduled_duration = 60m, got {session_report['scheduled_duration']}"
        p("7. PASS: _session_report_payload successfully decoupled actual attended duration (2m) from scheduled duration (60m)!")

        # 8. Verify _student_report_payload returns attended duration=2 and summary with 2 min
        student_report = _student_report_payload(db, test_session, student)
        p(f"8. Student report attendance: {student_report['attendance']}")
        p(f"8. Student report summary: {student_report['analysis']['summary']}")
        assert student_report["attendance"]["duration"] == 2, f"Expected student attendance duration = 2, got {student_report['attendance']['duration']}"
        assert student_report["attendance"]["attended_duration"] == 2, f"Expected attended_duration = 2, got {student_report['attendance']['attended_duration']}"
        assert "attended for 2 min" in student_report["analysis"]["summary"], "Expected 'attended for 2 min' in student analysis summary"
        p("8. PASS: _student_report_payload accurately reflects 2m attendance in metrics and summary text!")

        # 9. Verify improvement_loop and ReportGenerationAgent PDF summary with mocked LLM calls
        from app.agents.workflow import EduSenseAgentWorkflow
        workflow = EduSenseAgentWorkflow()
        with patch.object(workflow.lessons, "simplify_from_recommendation", return_value=AgentResult("LessonGenerationAgent", {"lesson": "Mocked"})), \
             patch.object(workflow.quizzes, "generate", return_value=AgentResult("QuizGenerationAgent", {"quiz": "Mocked"})):
            loop_res = workflow.improvement_loop(
                db,
                test_session.id,
                topic=test_session.title,
                instructor_name=instructor.name,
                session_title=test_session.title,
            )
            report_summary = loop_res["report"]["summary"]
            p(f"9. Generated PDF report summary: {report_summary}")
            assert "Attended duration: 2 min" in report_summary, f"Expected 'Attended duration: 2 min' in PDF report summary, got {report_summary}"
            p("9. PASS: PDF report summary accurately records attended duration: 2 min!")

        # 10. Verify student_my_sessions API endpoint calculation
        from app.api.sessions import student_my_sessions
        from starlette.requests import Request
        fake_req = Request({"type": "http", "method": "GET", "path": "/sessions/student/my-sessions", "headers": []})
        my_sessions = student_my_sessions(request=fake_req, db=db, user=student)
        target_s = next((s for s in my_sessions if s["id"] == test_session.id), None)
        assert target_s, "Test session not found in student_my_sessions"
        p(f"10. Student my-sessions item: duration={target_s['duration']}m, scheduled_duration={target_s['scheduled_duration']}m, attended={target_s['attended']}")
        assert target_s["duration"] == 2, f"Expected student session duration to be 2m, got {target_s['duration']}"
        assert target_s["attended_duration"] == 2, f"Expected attended_duration to be 2m, got {target_s['attended_duration']}"
        assert target_s["scheduled_duration"] == 60, f"Expected scheduled_duration to be 60m, got {target_s['scheduled_duration']}"
        p("10. PASS: student_my_sessions accurately reflects 2m attended duration for the student!")

        # 11. Clean up test records
        db.delete(log1)
        db.delete(log2)
        db.delete(log3)
        db.delete(reg)
        db.delete(test_session)
        db.commit()
        p("11. Test session and records cleaned up successfully.")

        p("\nALL TASK 2 VERIFICATION CHECKS PASSED SUCCESSFULLY!")

    finally:
        db.close()


if __name__ == "__main__":
    test_task2_reports_accuracy()
