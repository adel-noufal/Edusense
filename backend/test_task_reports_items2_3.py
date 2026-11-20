"""
Items 2+3 tests:
- report data-sufficiency thresholds (samples / participants / attended minutes)
- duration sanity cap (clamp, never reject)
- insufficient-data state in report payload + report agent summary
- CSV export: BOM, headers, quoting, per-student + timeline sections
- recommendation agent: insufficient -> empty; grounded LLM JSON validated;
  rule-based fallback cites computed facts
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from app.db.session import SessionLocal
from app.models.models import (
    EmotionLog,
    Session as ClassSession,
    SessionRegistration,
    User,
)
from app.services.report_data import (
    assess_session_data,
    clamp_duration,
    insufficient_data_message,
    session_metrics,
)
from app.api.reports import _csv_session_report, _session_report_payload
from app.agents.recommendation_agent import RecommendationAgent


def _mk_session(db, instructor_id, title="Threshold Test Session"):
    s = ClassSession(
        instructor_id=instructor_id, title=title, description="t",
        date=date.today(), start_time=time(10, 0), duration=60, status="ended",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_clamp_duration():
    assert clamp_duration(None) == (0.0, False)
    assert clamp_duration(-5) == (0.0, False)
    assert clamp_duration(0) == (0.0, False)
    val, capped = clamp_duration(100.0)
    assert val == 100.0 and capped is False
    val, capped = clamp_duration(99999.0)
    assert capped is True and val > 0  # clamped to configured cap


def test_assess_and_csv_and_payload():
    db = SessionLocal()
    created = []
    try:
        instructor = db.query(User).filter_by(role="instructor").first()
        student = db.query(User).filter_by(role="student").first()
        assert instructor and student

        # --- Empty session: insufficient ---
        s_empty = _mk_session(db, instructor.id, "Empty Threshold Session")
        created.append(s_empty.id)
        a = assess_session_data(db, s_empty.id)
        assert a["sufficient"] is False
        assert "participants" in a["missing"]
        assert "emotion_samples" in a["missing"]
        msg = insufficient_data_message(a)
        assert "Not enough data" in msg

        payload = _session_report_payload(db, s_empty)
        assert payload["sufficient_data"] is False
        assert payload["insufficient_data_message"]
        assert payload["engagement_percentage"] is None  # no fabricated score

        # --- Rich session: sufficient ---
        s_rich = _mk_session(db, instructor.id, "Rich Threshold Session")
        created.append(s_rich.id)
        t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.add(SessionRegistration(session_id=s_rich.id, student_id=student.id,
                                   attended=True, joined_at=t0, left_at=t0 + timedelta(minutes=10)))
        for i in range(12):
            db.add(EmotionLog(session_id=s_rich.id, student_id=student.id,
                              emotion="happy" if i % 3 else "neutral",
                              confidence=0.9, timestamp=t0 + timedelta(seconds=30 * i)))
        db.commit()

        a2 = assess_session_data(db, s_rich.id)
        assert a2["sufficient"] is True, a2
        metrics = session_metrics(db, s_rich.id, a2)
        assert metrics["emotion_samples"] == 12
        assert metrics["participants"] == 1
        assert metrics["attended_minutes"] >= 2

        # --- CSV export ---
        csv_text = _csv_session_report(db, s_rich, lang="en")
        assert csv_text.startswith("﻿")  # BOM for Excel/Arabic
        assert "Session" in csv_text and "Emotion Timeline" in csv_text
        assert "happy" in csv_text and "neutral" in csv_text
        # quoting: title has no commas here, but check csv module didn't break
        lines = [l for l in csv_text.splitlines() if l.strip()]
        assert len(lines) > 10
        # Arabic headers
        csv_ar = _csv_session_report(db, s_rich, lang="ar")
        assert "القسم" in csv_ar

        # --- Duration cap on payload ---
        with patch("app.services.report_data.get_settings") as gs:
            gs.return_value.report_max_attended_minutes = 5.0
            val, capped = clamp_duration(30.0)
            assert capped and val == 5.0
    finally:
        # cleanup created sessions + dependent rows
        for sid in created:
            db.query(EmotionLog).filter_by(session_id=sid).delete()
            db.query(SessionRegistration).filter_by(session_id=sid).delete()
            db.query(ClassSession).filter_by(id=sid).delete()
        db.commit()
        db.close()


def test_recommendations_insufficient_and_grounded():
    agent = RecommendationAgent()
    engagement = {"engagement_percentage": 40.0, "has_data": True,
                  "attention_timeline": [], "participation": {}}
    emotions = {"distribution": {"happy": 50.0, "sad": 30.0}, "samples": 5}

    # insufficient -> empty, honest
    res = agent.recommend(engagement, emotions,
                          metrics={"participants": 1, "attended_minutes": 1.0,
                                   "sufficient_data": False}).data
    assert res["insufficient_data"] is True
    assert res["recommendations"] == []

    # no data at all -> empty
    res2 = agent.recommend({"engagement_percentage": None, "has_data": False,
                            "attention_timeline": []}, {"distribution": {}, "samples": 0}).data
    assert res2["insufficient_data"] is True

    # sufficient + LLM failure -> rule-based fallback with evidence
    with patch("app.agents.recommendation_agent.generate_json_any",
               side_effect=Exception("provider down")):
        res3 = agent.recommend(engagement, emotions,
                               metrics={"participants": 2, "attended_minutes": 10.0,
                                        "sufficient_data": True}).data
    assert res3["insufficient_data"] is False
    assert len(res3["recommendations"]) >= 1
    details = res3.get("recommendation_details") or []
    assert all(d.get("evidence") for d in details)  # every rec cites evidence

    # sufficient + LLM returns schema-valid grounded JSON
    fake = {"recommendations": [
        {"text": "Address the sadness spike.", "evidence": "Sad emotion reached 30% of frames."},
        {"text": "", "evidence": "missing text -> dropped"},
        {"text": "No evidence -> dropped", "evidence": ""},
    ]}
    with patch("app.agents.recommendation_agent.generate_json_any", return_value=fake):
        res4 = agent.recommend(engagement, emotions,
                               metrics={"participants": 2, "attended_minutes": 10.0,
                                        "sufficient_data": True}).data
    assert res4["recommendations"] == ["Address the sadness spike."]


if __name__ == "__main__":
    test_clamp_duration()
    test_assess_and_csv_and_payload()
    test_recommendations_insufficient_and_grounded()
    print("ALL REPORT/RECOMMENDATION CHECKS PASSED")
