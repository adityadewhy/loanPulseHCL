"""
app/routers/repayments.py — Repayment schedule inspection, payment recording, and overdue tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import date
from typing import List
import csv
import io

from app.database import get_async_db
from app.models import LoanApplication, RepaymentSchedule, AuditLog, User
from app.schemas import (
    RepaymentScheduleResponse, RecordPaymentRequest, RepaymentSummary
)
from app.services.notification_service import record_notification
from app.services.scheduler import run_overdue_check, run_upcoming_reminders
from app.auth.utils import get_current_user

router = APIRouter(prefix="/repayments", tags=["Repayments"])


@router.get("/{loan_id}", response_model=RepaymentSummary)
async def get_repayment_schedule(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get full repayment schedule and calculated summary metrics for a loan.
    """
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    result = await db.execute(
        select(RepaymentSchedule)
        .where(RepaymentSchedule.loan_id == loan_id)
        .order_by(RepaymentSchedule.installment_number)
    )
    schedule = result.scalars().all()

    total_installments = len(schedule)
    paid_count = sum(1 for s in schedule if s.status == "PAID")
    overdue_count = sum(1 for s in schedule if s.status == "OVERDUE")
    pending_count = sum(1 for s in schedule if s.status == "PENDING")
    total_emi = sum(s.emi_amount for s in schedule)
    total_paid = sum(s.paid_amount or 0.0 for s in schedule)
    outstanding_balance = max(0.0, total_emi - total_paid)

    return RepaymentSummary(
        loan_id=loan_id,
        total_installments=total_installments,
        paid_count=paid_count,
        overdue_count=overdue_count,
        pending_count=pending_count,
        total_emi=round(total_emi, 2),
        total_paid=round(total_paid, 2),
        outstanding_balance=round(outstanding_balance, 2),
        schedule=schedule,
    )


@router.post("/{loan_id}/pay/{installment_id}", response_model=RepaymentScheduleResponse)
async def record_payment(
    loan_id: int,
    installment_id: int,
    payload: RecordPaymentRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record payment against a specific installment:
    1. Validates installment belongs to loan.
    2. Marks status as PAID.
    3. Records paid_amount and paid_date.
    4. Automatically transitions loan to 'ACTIVE' (if first payment) or 'CLOSED' (if all paid).
    5. Logs audit entry and sends payment receipt notification.
    """
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    installment = await db.get(RepaymentSchedule, installment_id)
    if not installment or installment.loan_id != loan_id:
        raise HTTPException(status_code=404, detail="Installment not found for this loan")

    if installment.status == "PAID":
        raise HTTPException(status_code=400, detail="Installment is already fully paid")

    old_status = installment.status
    installment.status = "PAID"
    installment.paid_amount = payload.paid_amount
    installment.paid_date = payload.paid_date or date.today()

    # Check if this closes the loan
    all_installments_res = await db.execute(
        select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)
    )
    all_installments = all_installments_res.scalars().all()
    unpaid = [i for i in all_installments if i.id != installment_id and i.status != "PAID"]

    if not unpaid:
        loan.status = "CLOSED"
    elif loan.status == "DISBURSED":
        loan.status = "ACTIVE"

    # Audit Trail
    db.add(AuditLog(
        loan_id=loan_id,
        actor_id=current_user.id,
        action="PAYMENT_RECORDED",
        old_value=old_status,
        new_value="PAID",
        notes=f"Paid ${payload.paid_amount:,.2f} for installment #{installment.installment_number} by {current_user.full_name}",
    ))

    # Payment Receipt Notification
    recipient = loan.applicant_email or f"applicant_{loan.id}@example.com"
    await record_notification(
        db=db,
        recipient_email=recipient,
        event="PAYMENT_CONFIRMATION",
        subject=f"Payment Receipt: Installment #{installment.installment_number} (Loan #{loan.id})",
        body=(
            f"Dear {loan.applicant_name},\n\n"
            f"We received your payment of ${payload.paid_amount:,.2f} for installment #{installment.installment_number}.\n"
            f"Date: {installment.paid_date}\n\n"
            f"Thank you for your timely repayment!"
        ),
        loan_id=loan.id,
        send_email_copy=True,
    )

    await db.commit()
    await db.refresh(installment)
    return installment


@router.get("/overdue/all", response_model=List[RepaymentScheduleResponse])
async def list_all_overdue(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List all overdue installments across the entire platform."""
    result = await db.execute(
        select(RepaymentSchedule)
        .where(RepaymentSchedule.status == "OVERDUE")
        .order_by(RepaymentSchedule.due_date.asc())
    )
    return result.scalars().all()


@router.post("/batch/trigger-overdue-check")
async def trigger_overdue_check(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually triggers the background overdue scan and notification dispatches.
    """
    overdue_summary = await run_overdue_check(db)
    reminder_summary = await run_upcoming_reminders(db)
    return {
        "status": "success",
        "overdue_check": overdue_summary,
        "upcoming_reminders": reminder_summary,
    }


@router.get("/{loan_id}/export-csv")
async def export_repayment_schedule_csv(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Export loan amortization repayment schedule as a CSV file."""
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    result = await db.execute(
        select(RepaymentSchedule)
        .where(RepaymentSchedule.loan_id == loan_id)
        .order_by(RepaymentSchedule.installment_number)
    )
    schedule = result.scalars().all()
    if not schedule:
        raise HTTPException(status_code=400, detail="No repayment schedule found for this loan")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Installment Number",
        "Due Date",
        "Monthly EMI ($)",
        "Principal Component ($)",
        "Interest Component ($)",
        "Penalty ($)",
        "Status",
        "Paid Date",
        "Paid Amount ($)",
    ])
    for s in schedule:
        writer.writerow([
            s.installment_number,
            str(s.due_date),
            f"{s.emi_amount:.2f}",
            f"{s.principal_component:.2f}",
            f"{s.interest_component:.2f}",
            f"{s.penalty_amount:.2f}",
            s.status,
            str(s.paid_date or ""),
            f"{s.paid_amount:.2f}" if s.paid_amount is not None else "",
        ])

    csv_data = output.getvalue()
    safe_name = loan.applicant_name.replace(" ", "_")
    filename = f"loan_{loan_id}_{safe_name}_amortization.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

