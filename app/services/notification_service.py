"""
app/services/notification_service.py — Email and In-App notification service.
Uses free aiosmtplib (Gmail SMTP) when credentials provided, and logs safely otherwise.
Always persists in-app notifications to PostgreSQL.
"""
import logging
from email.message import EmailMessage
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import aiosmtplib

from app.config import settings
from app.models import Notification

logger = logging.getLogger("notification_service")


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Sends an email using aiosmtplib (TLS/STARTTLS on port 587).
    Gracefully logs and returns False if SMTP credentials are not configured.
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.info(f"[Email Simulated] To: {to_email} | Subject: {subject} | Body: {body}")
        return False

    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info(f"[Email Sent] Successfully delivered to {to_email}")
        return True
    except Exception as e:
        logger.error(f"[Email Failed] Error sending to {to_email}: {e}")
        return False


async def record_notification(
    db: AsyncSession,
    recipient_email: str,
    event: str,
    subject: str,
    body: str,
    loan_id: Optional[int] = None,
    notif_type: str = "IN_APP",
    send_email_copy: bool = True,
) -> Notification:
    """
    Creates an in-app notification record and optionally sends an email copy.
    """
    email_sent = False
    if send_email_copy and recipient_email:
        email_sent = await send_email(recipient_email, subject, body)

    notif = Notification(
        recipient_email=recipient_email,
        loan_id=loan_id,
        type=notif_type,
        event=event,
        subject=subject,
        body=body,
        status="SENT" if email_sent else "PENDING",
        sent_at=datetime.now(timezone.utc) if email_sent else None,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif
