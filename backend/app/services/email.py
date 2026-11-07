import smtplib
from email.message import EmailMessage
from app.core.config import get_settings
import asyncio


def _send_email_sync(to_email: str, subject: str, html_body: str):
  settings = get_settings()

  if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
    raise RuntimeError("SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD.")

  msg = EmailMessage()
  msg["Subject"] = subject
  msg["From"] = settings.smtp_from_email or settings.smtp_user
  msg["To"] = to_email
  msg.set_content("This is an HTML email. Please view in an HTML-capable client.")
  msg.add_alternative(html_body, subtype="html")

  try:
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    server.starttls()
    server.login(settings.smtp_user, settings.smtp_password)
    server.send_message(msg)
    server.quit()
  except Exception as e:
    # Raise so caller (and logs) can detect failure instead of silently continuing
    raise

async def send_session_reminder_email(emails: list[str], session_title: str, start_time_str: str, link: str):
    subject = f"Your session '{session_title}' is starting soon!"
    
    for email in emails:
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
              <h2 style="color: #0ea5e9;">EduSense AI Platform</h2>
              <p>Hello,</p>
              <p>This is a quick reminder that your registered session <strong>{session_title}</strong> is scheduled to start at <strong>{start_time_str}</strong>.</p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{link}" style="background-color: #0ea5e9; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                  Join Session Now
                </a>
              </div>
              <p style="font-size: 0.9em; color: #666;">If the button doesn't work, copy and paste this link into your browser:</p>
              <p style="font-size: 0.9em; color: #666;"><a href="{link}">{link}</a></p>
              <hr style="border: none; border-top: 1px solid #eee; margin-top: 30px;" />
              <p style="font-size: 0.8em; color: #999; text-align: center;">You are receiving this because you registered for a session on EduSense.</p>
            </div>
          </body>
        </html>
        """
        # Run synchronous SMTP in thread pool to not block FastAPI
        await asyncio.to_thread(_send_email_sync, email, subject, html_body)


async def send_reset_password_email(to_email: str, reset_link: str):
    subject = "Reset your EduSense Password"
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
          <h2 style="color: #0ea5e9;">EduSense AI Platform</h2>
          <p>Hello,</p>
          <p>We received a request to reset the password for your account.</p>
          <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background-color: #0ea5e9; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">
              Reset Password
            </a>
          </div>
          <p style="font-size: 0.9em; color: #666;">If you didn't request a password reset, you can safely ignore this email.</p>
          <p style="font-size: 0.9em; color: #666;">If the button doesn't work, copy and paste this link into your browser:</p>
          <p style="font-size: 0.9em; color: #666;"><a href="{reset_link}">{reset_link}</a></p>
        </div>
      </body>
    </html>
    """
    await asyncio.to_thread(_send_email_sync, to_email, subject, html_body)
