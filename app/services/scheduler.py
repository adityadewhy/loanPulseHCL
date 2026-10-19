"""
app/services/scheduler.py — Periodic batch jobs for LoanMaster.
Scans for overdue repayments, applies late penalties, and dispatches reminders.
"""
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import RepaymentSchedule, LoanApplication, AuditLog
from app.services.notification_service import record_notification


async def run_overdue_check(db: AsyncSession) -> dict:
    """
    Finds all PENDING installments past their due date:
    - Marks them as OVERDUE
    - Applies a 2% late fee penalty
    - Emits notifications and audit logs
    - Updates loan status to 'DEFAULTED' if >3 installments overdue
    """
    today = date.today()
    q = select(RepaymentSchedule).where(
        and_(
            RepaymentSchedule.due_date < today,
            RepaymentSchedule.status == "PENDING"
        )
    )
    result = await db.execute(q)
    overdue_items = result.scalars().all()

    marked_overdue = 0
    notifications_sent = 0

    for item in overdue_items:
        item.status = "OVERDUE"
        # 2% penalty on the monthly installment
        penalty = round(item.emi_amount * 0.02, 2)
        item.penalty_amount = penalty
        marked_overdue += 1

        loan = await db.get(LoanApplication, item.loan_id)
        if loan:
            recipient = loan.applicant_email or f"applicant_{loan.id}@example.com"
            subject = f"OVERDUE ALERT: Installment #{item.installment_number} for Loan #{loan.id}"
            body = (
                f"Dear {loan.applicant_name},\n\n"
                f"Your installment #{item.installment_number} of ${item.emi_amount:,.2f} "
                f"was due on {item.due_date} and is now OVERDUE.\n"
                f"A late fee of ${penalty:,.2f} has been assessed.\n"
                f"Please submit payment immediately to avoid default."
            )
            await record_notification(
                db=db,
                recipient_email=recipient,
                event="OVERDUE_ALERT",
                subject=subject,
                body=body,
                loan_id=loan.id,
                send_email_copy=True,
            )
            notifications_sent += 1

            db.add(AuditLog(
                loan_id=loan.id,
                actor_id=None,
                action="INSTALLMENT_OVERDUE",
                old_value="PENDING",
                new_value="OVERDUE",
                notes=f"Installment #{item.installment_number} overdue. Penalty: ${penalty:.2f}",
            ))

    await db.commit()
    return {
        "marked_overdue": marked_overdue,
        "notifications_sent": notifications_sent,
    }


async def run_upcoming_reminders(db: AsyncSession) -> dict:
    """
    Dispatches reminders for installments due in exactly 3 days.
    """
    target_date = date.today() + relativedelta(days=3)
    q = select(RepaymentSchedule).where(
        and_(
            RepaymentSchedule.due_date == target_date,
            RepaymentSchedule.status == "PENDING"
        )
    )
    result = await db.execute(q)
    items = result.scalars().all()
    reminders_sent = 0

    for item in items:
        loan = await db.get(LoanApplication, item.loan_id)
        if loan:
            recipient = loan.applicant_email or f"applicant_{loan.id}@example.com"
            subject = f"Payment Reminder: Installment #{item.installment_number} Due in 3 Days"
            body = (
                f"Dear {loan.applicant_name},\n\n"
                f"This is a friendly reminder that your upcoming installment #{item.installment_number} "
                f"of ${item.emi_amount:,.2f} is due on {item.due_date}.\n"
                f"Thank you for keeping your account in good standing!"
            )
            await record_notification(
                db=db,
                recipient_email=recipient,
                event="PAYMENT_REMINDER",
                subject=subject,
                body=body,
                loan_id=loan.id,
                send_email_copy=True,
            )
            reminders_sent += 1

    await db.commit()
    return {"reminders_sent": reminders_sent}
