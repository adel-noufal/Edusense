"""One rule for timestamps leaving the API (issue U2).

SQLite returns naive datetimes even for ``DateTime(timezone=True)`` columns, so
``.isoformat()`` used to emit "2026-11-23T06:19:00" with no zone. A browser then
read that string as local time, which shifted every displayed time by the UTC
offset (2 h in Africa/Cairo). Everything the API sends is now ISO-8601 UTC with
an explicit ``Z``; the frontend converts it to the browser timezone.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone


def iso_z(value) -> str | None:
    """Serialize a datetime as UTC ISO-8601 ending in ``Z``.

    Naive values are interpreted as UTC (that is how they are stored), never as
    server-local time. Dates and times are passed through so callers that reuse
    this helper for mixed records keep working.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, str) and "T" in value:
        # Timestamps already stored as text (vector-store metadata, legacy rows)
        # are normalised too, so "+00:00" and naive strings both become "Z".
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return iso_z(parsed)
        except ValueError:
            return value
    return str(value)
