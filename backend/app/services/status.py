from datetime import datetime, timezone


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
