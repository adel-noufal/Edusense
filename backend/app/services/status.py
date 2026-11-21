from datetime import datetime, timezone, timedelta

from app.core.config import get_settings

# Stored statuses that mean "the instructor cancelled this session"
_CANCELLED = {"cancelled", "canceled"}
# Stored statuses that mean the session ran its course
_ENDED = {"ended", "completed", "finished"}
# Stored statuses that mean the session is currently running
_LIVE = {"ongoing", "live", "active"}
# Stored statuses that mean "scheduled but not yet started"
_SCHEDULED = {"pending", "scheduled", "upcoming", "preparing"}


def _session_start(item) -> datetime:
    return datetime.combine(item.date, item.start_time)


def session_end(item) -> datetime | None:
    """Scheduled end datetime, or None when the session has no time limit."""
    if getattr(item, "duration", None) is None:
        return None
    return _session_start(item) + timedelta(minutes=int(item.duration))


def effective_status(item, now: datetime | None = None) -> str:
    """
    Derive the *effective* status from the stored status plus the schedule.
    Never rely on the stored status alone — a 'pending' session whose start
    time passed days ago is 'missed', not 'upcoming'.

    Returns one of: cancelled, ended, live, upcoming, missed.
    """
    now = now or datetime.now().replace(tzinfo=None)
    stored = (item.status or "").lower()

    if stored in _CANCELLED:
        return "cancelled"
    if stored in _ENDED:
        return "ended"
    if stored == "missed":
        return "missed"

    start = _session_start(item)
    end = session_end(item)

    # 'preparing' is a pre-live instructor state — never "missed"; the
    # preparing -> ongoing transition is handled by refresh_status.
    if stored == "preparing":
        return "upcoming"

    if stored in _LIVE:
        # A live session with a time limit that already elapsed is stale -> ended
        if end is not None and now > end:
            return "ended"
        return "live"

    if stored in _SCHEDULED:
        if now < start:
            return "upcoming"
        # Start time passed but the instructor never started it. Within the
        # grace window it may still go live; afterwards it is 'missed'.
        grace = timedelta(minutes=int(get_settings().session_missed_grace_minutes))
        if now <= start + grace:
            return "upcoming"
        return "missed"

    # Unknown stored status: derive purely from the schedule
    if now < start:
        return "upcoming"
    if end is not None and now > end:
        return "ended"
    return "live"


def session_status(date_value, start_time, duration: int | None) -> str:
    """
    Derive display status. `duration=None` means the session has no time
    limit — it stays "ongoing" after start until the instructor ends it
    manually (status is stored on the row, this is only a fallback).
    """
    start = datetime.combine(date_value, start_time)
    now = datetime.now().replace(tzinfo=None)
    if now < start:
        return "pending"
    if duration is None:
        return "ongoing"
    end = start.replace(tzinfo=None).timestamp() + duration * 60
    if now.timestamp() <= end:
        return "ongoing"
    return "ended"
