"""
app/routers/notifications.py — Notification inspection and status updates.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timezone
from typing import List, Optional

from app.database import get_async_db
from app.models import Notification, User
from app.schemas import NotificationResponse
from app.auth.utils import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    loan_id: Optional[int] = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List recent notifications."""
    q = select(Notification).order_by(Notification.created_at.desc())
    if loan_id:
        q = q.where(Notification.loan_id == loan_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    q = q.limit(limit)

    result = await db.execute(q)
    return result.scalars().all()


@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Get count of unread in-app notifications."""
    result = await db.execute(
        select(func.count(Notification.id)).where(Notification.read_at.is_(None))
    )
    return {"unread_count": result.scalar() or 0}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an in-app notification as read."""
    notif = await db.get(Notification, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notif)
    return notif
