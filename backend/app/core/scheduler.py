from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.models import Session, SessionRegistration, User
from app.services.email import send_session_reminder_email
from datetime import datetime
import asyncio
import math

settings = get_settings()

scheduler = AsyncIOScheduler()

async def check_upcoming_sessions():
    """
    Checks the database for sessions starting soon that haven't sent a reminder yet.
    """
    db = SessionLocal()
    try:
        now = datetime.now()
        
        # We define 'soon' as starting within the next 15 minutes
        sessions = db.query(Session).filter(
            Session.status == "pending",
            Session.reminder_sent == False
        ).all()
        
        print(f"Scheduler check: Found {len(sessions)} pending sessions without reminders")
        
        for session in sessions:
            # Combine date and time into a single datetime object
            session_start = datetime.combine(session.date, session.start_time)
            time_until_start = (session_start - now).total_seconds() / 60.0
            
            print(f"Session '{session.title}' starts in {time_until_start:.1f} minutes")
            
            # If the session starts in less than 15 minutes
            minutes_left = math.floor(time_until_start)

            # Send minute-based reminders from 15 down to 1
            if 1 <= minutes_left <= 15:
                sent_minutes = set()
                if session.reminders_sent:
                    sent_minutes = set(x for x in session.reminders_sent.split(',') if x)

                if str(minutes_left) in sent_minutes:
                    # already sent this minute reminder
                    continue

                # proceed to send reminder for this minute
                # Find all registered students
                registrations = db.query(SessionRegistration).filter(SessionRegistration.session_id == session.id).all()
                student_ids = [reg.student_id for reg in registrations]
                
                emails = []
                if student_ids:
                    students = db.query(User).filter(User.id.in_(student_ids)).all()
                    emails.extend([student.email for student in students if student.email])
                
                # Add instructor's email
                instructor = db.query(User).filter(User.id == session.instructor_id).first()
                if instructor and instructor.email:
                    emails.append(instructor.email)
                
                print(f"Found {len(emails)} email addresses for session '{session.title}'")
                
                if emails:
                    start_time_str = session_start.strftime("%A, %B %d at %I:%M %p")
                    link = f"{settings.frontend_url}/student/sessions/{session.id}/live"
                    
                    # Send email
                    await send_session_reminder_email(emails, session.title, start_time_str, link)

                    # record that we've sent this minute reminder
                    sent_minutes.add(str(minutes_left))
                    session.reminders_sent = ','.join(sorted(sent_minutes, key=lambda x: int(x)))
                    db.commit()
                    print(f"Reminder sent for session: {session.title} (minute {minutes_left})")
            elif time_until_start < 0:
                # Session already started, mark reminder as sent to avoid retrying
                session.reminder_sent = True
                db.commit()
                print(f"Session '{session.title}' already started, skipping reminder")

    except Exception as e:
        print(f"Scheduler error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(check_upcoming_sessions, 'interval', minutes=1)
    scheduler.start()
    print("APScheduler background task started.")

def shutdown_scheduler():
    scheduler.shutdown()
    print("APScheduler shutdown.")
