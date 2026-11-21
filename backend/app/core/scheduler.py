import asyncio
from datetime import datetime
import logging
import math
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.models import Session, SessionRegistration, User
from app.services.email import send_session_reminder_email

logger = logging.getLogger("app.core.scheduler")
settings = get_settings()

scheduler = AsyncIOScheduler()

async def check_upcoming_sessions():
    """
    Checks the database for sessions starting soon that haven't sent a reminder yet.
    Also reconciles stale session statuses (missed/ended) once per run.
    """
    db = SessionLocal()
    try:
        from app.api.sessions import reconcile_session_statuses
        changed = reconcile_session_statuses(db)
        if changed:
            logger.info("Scheduler: reconciled %d stale session statuses", changed)

        now = datetime.now()
        
        # Only check active/pending sessions that haven't had final reminder sent
        sessions = db.query(Session).filter(
            Session.status.in_(["pending", "scheduled", "upcoming"]),
            Session.reminder_sent == False
        ).all()
        
        logger.debug("Scheduler check: Found %d pending sessions without reminders", len(sessions))
        
        for session in sessions:
            session_start = datetime.combine(session.date, session.start_time)
            time_until_start = (session_start - now).total_seconds() / 60.0
            
            logger.debug("Session '%s' starts in %.1f minutes", session.title, time_until_start)
            
            # If the session starts in less than 15 minutes
            minutes_left = math.floor(time_until_start)

            # Send minute-based reminders from 15 down to 1
            if 1 <= minutes_left <= 15:
                sent_minutes = set()
                if session.reminders_sent:
                    sent_minutes = set(x for x in session.reminders_sent.split(',') if x)

                if str(minutes_left) in sent_minutes:
                    continue

                # proceed to send reminder for this minute
                registrations = db.query(SessionRegistration).filter(SessionRegistration.session_id == session.id).all()
                student_ids = [reg.student_id for reg in registrations]
                
                emails = []
                if student_ids:
                    students = db.query(User).filter(User.id.in_(student_ids)).all()
                    emails.extend([student.email for student in students if student.email])
                
                instructor = db.query(User).filter(User.id == session.instructor_id).first()
                if instructor and instructor.email:
                    emails.append(instructor.email)
                
                if emails:
                    start_time_str = session_start.strftime("%A, %B %d at %I:%M %p")
                    link = f"{settings.frontend_url}/student/sessions/{session.id}/live"
                    
                    await send_session_reminder_email(emails, session.title, start_time_str, link)

                    sent_minutes.add(str(minutes_left))
                    session.reminders_sent = ','.join(sorted(sent_minutes, key=lambda x: int(x)))
                    db.commit()
                    logger.info("Reminder sent for session: %s (minute %d)", session.title, minutes_left)
            elif time_until_start < 0:
                # Session already started or passed, mark reminder as sent to avoid retrying
                session.reminder_sent = True
                db.commit()
                logger.debug("Session '%s' already started/passed, marked reminder_sent", session.title)

    except Exception as e:
        logger.error("Scheduler error: %s", e, exc_info=True)
    finally:
        db.close()

def start_scheduler():
    try:
        scheduler.add_job(check_upcoming_sessions, 'interval', minutes=1)
        scheduler.start()
        print("APScheduler background task started.")
    except Exception as e:
        print(f"APScheduler note: {e}")

def shutdown_scheduler():
    try:
        if scheduler.running:
            scheduler.shutdown()
            print("APScheduler shutdown.")
    except Exception:
        pass
