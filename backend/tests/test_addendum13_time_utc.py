"""U2 regression: timestamps leave the API as ISO-8601 UTC and the UI converts them.

The visible symptom was a question asked at 08:19 showing "06:19 AM" in the
Knowledge Base: the API emitted a naive datetime, the browser read it as local
time, and Africa/Cairo (UTC+2) lost two hours.

Runs offline (no providers, no server) so it can live in the pytest stage.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.services.timefmt import iso_z


def test_naive_datetime_is_utc_not_local():
    value = iso_z(datetime(2026, 11, 23, 6, 19, 0))
    assert value == "2026-11-23T06:19:00Z", value


def test_aware_datetime_is_normalised_to_utc():
    cairo = ZoneInfo("Africa/Cairo")
    value = iso_z(datetime(2026, 11, 23, 8, 19, 0, tzinfo=cairo))
    assert value == "2026-11-23T06:19:00Z", value


def test_cairo_round_trip_shows_8_19_for_a_utc_6_19_record():
    """The exact number pair from the complaint."""
    stored = iso_z(datetime(2026, 11, 23, 6, 19, 0))  # 06:19 UTC in the DB
    parsed = datetime.fromisoformat(stored.replace("Z", "+00:00"))
    assert parsed.astimezone(ZoneInfo("Africa/Cairo")).strftime("%H:%M") == "08:19"


def test_none_and_dates_pass_through():
    assert iso_z(None) is None
    assert iso_z(date(2026, 11, 23)) == "2026-11-23"


def test_every_api_module_uses_the_shared_serializer():
    """A new endpoint cannot reintroduce the naive isoformat() bug."""
    offenders = []
    for root, _dirs, files in os.walk(os.path.join(BACKEND_ROOT, "app")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            # timefmt.py is the one place allowed to call isoformat(): it is the
            # serializer that guarantees the trailing Z.
            if os.path.basename(path) == "timefmt.py":
                continue
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for match in re.finditer(r"\.isoformat\(\)", text):
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{os.path.relpath(path, BACKEND_ROOT)}:{line}")
    assert not offenders, "naive isoformat() still serialises API timestamps: " + ", ".join(offenders)


def test_frontend_formats_api_timestamps_with_the_utc_helper():
    """Pages must not read raw API timestamps as local time."""
    frontend = os.path.join(os.path.dirname(BACKEND_ROOT), "frontend", "src")
    helper = os.path.join(frontend, "services", "time.js")
    assert os.path.exists(helper), "frontend/src/services/time.js is missing"
    offenders = []
    for root, _dirs, files in os.walk(frontend):
        for name in files:
            if not name.endswith((".jsx", ".js")) or name == "time.js":
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for match in re.finditer(r"new Date\([^)]*(_at|timestamp|ingested_at)[^)]*\)\.toLocale", text):
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{os.path.relpath(path, frontend)}:{line}")
    assert not offenders, "raw API timestamps formatted as local time: " + ", ".join(offenders)
