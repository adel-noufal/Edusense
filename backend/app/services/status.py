from datetime import datetime, timezone


def session_status(date_value, start_time, duration: int) -> str:
    start = datetime.combine(date_value, start_time)
    now = datetime.now().replace(tzinfo=None)
    end = start.replace(tzinfo=None).timestamp() + duration * 60
    if now < start:
        return "pending"
    if now.timestamp() <= end:
        return "ongoing"
    return "ended"
