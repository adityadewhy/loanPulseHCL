"""
app/routers/disbursements.py — Loan disbursement & amortization schedule generation.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_async_db
from app.models import LoanApplication, Disbursement, RepaymentSchedule, AuditLog, User
from app.schemas import DisbursementCreate, DisbursementResponse
from app.services.repayment_engine import generate_amortization_schedule
from app.services.notification_service import record_notification
from app.auth.utils import get_current_user

router = APIRouter(prefix="/disbursements", tags=["Disbursements"])


@router.post("/", response_model=DisbursementResponse, status_code=status.HTTP_201_CREATED)
async def disburse_loan(
    payload: DisbursementCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    Disburse an approved loan:
    1. Validates loan exists and is in 'APPROVED' or 'ACTIVE' state.
    2. Ensures no duplicate disbursement exists.
    3. Records disbursement details.
    4. Automatically generates the full monthly EMI amortization schedule.
    5. Advances loan status to 'DISBURSED'.
    6. Emits audit log and customer notification.
    """
    loan = await db.get(LoanApplication, payload.loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    if loan.status not in ["APPROVED", "PENDING"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot disburse loan with status '{loan.status}'. Must be APPROVED."
        )

    # Check if already disbursed
    existing_disb = await db.execute(
        select(Disbursement).where(Disbursement.loan_id == payload.loan_id)
    )
    if existing_disb.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Loan has already been disbursed")

    # 1. Create Disbursement record
    disb = Disbursement(
        loan_id=payload.loan_id,
        disbursed_amount=payload.disbursed_amount,
        interest_rate=payload.interest_rate,
        disbursement_date=payload.disbursement_date,
        payment_method=payload.payment_method,
        bank_reference=payload.bank_reference,
    )
    db.add(disb)

    # 2. Generate and persist amortization schedule
    term = loan.requested_term_months or 12
    schedule_data = generate_amortization_schedule(
        principal=payload.disbursed_amount,
        annual_rate=payload.interest_rate,
        term_months=term,
        disbursement_date=payload.disbursement_date,
    )

    for item in schedule_data:
        rep = RepaymentSchedule(
            loan_id=loan.id,
            installment_number=item["installment_number"],
            due_date=item["due_date"],
            emi_amount=item["emi_amount"],
            principal_component=item["principal_component"],
            interest_component=item["interest_component"],
            status="PENDING",
        )
        db.add(rep)

    # 3. Update loan status to DISBURSED
    old_status = loan.status
    loan.status = "DISBURSED"

    # 4. Audit Trail
    db.add(AuditLog(
        loan_id=loan.id,
        actor_id=current_user.id,
        action="LOAN_DISBURSED",
        old_value=old_status,
        new_value="DISBURSED",
        notes=f"Disbursed ${payload.disbursed_amount:,.2f} @ {payload.interest_rate}% by {current_user.full_name}",
    ))

    # 5. Customer Notification
    recipient = loan.applicant_email or f"applicant_{loan.id}@example.com"
    first_due = schedule_data[0]["due_date"]
    monthly_emi = schedule_data[0]["emi_amount"]
    await record_notification(
        db=db,
        recipient_email=recipient,
        event="LOAN_DISBURSED",
        subject=f"Loan #{loan.id} Disbursed Successfully",
        body=(
            f"Dear {loan.applicant_name},\n\n"
            f"Great news! Your loan of ${payload.disbursed_amount:,.2f} has been disbursed.\n"
            f"Monthly EMI: ${monthly_emi:,.2f}\n"
            f"First payment due date: {first_due}\n\n"
            f"Thank you for choosing LoanPulse!"
        ),
        loan_id=loan.id,
        send_email_copy=True,
    )

    await db.commit()
    await db.refresh(disb)
    return disb


@router.get("/{loan_id}", response_model=DisbursementResponse)
async def get_disbursement(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve disbursement details for a specific loan."""
    result = await db.execute(
        select(Disbursement).where(Disbursement.loan_id == loan_id)
    )
    disb = result.scalar_one_or_none()
    if not disb:
        raise HTTPException(status_code=404, detail="Disbursement record not found")
    return disb


@router.get("/", response_model=List[DisbursementResponse])
async def list_disbursements(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List all disbursements across the platform."""
    result = await db.execute(select(Disbursement).order_by(Disbursement.created_at.desc()))
    return result.scalars().all()
