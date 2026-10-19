"""
app/routers/applications.py — Loan application CRUD + lifecycle management.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_async_db
from app.models import LoanApplication, AuditLog
from app.schemas import (
    LoanApplicationCreate, LoanApplicationResponse,
    LoanApplicationDetailResponse, LoanStatusUpdate, AuditLogResponse,
)
from app.services import evaluate_loan_risk
from app.auth.utils import get_current_user
from app.models import User

router = APIRouter(prefix="/applications", tags=["Loan Applications"])


@router.post("/", response_model=LoanApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application: LoanApplicationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a new loan application. Risk evaluation runs in background."""
    db_loan = LoanApplication(
        **application.model_dump(),
        assigned_officer_id=current_user.id,
    )
    db.add(db_loan)
    await db.commit()
    await db.refresh(db_loan)

    # Audit
    db.add(AuditLog(
        loan_id=db_loan.id,
        actor_id=current_user.id,
        action="APPLICATION_SUBMITTED",
        new_value="PENDING",
        notes=f"Submitted by {current_user.full_name}",
    ))
    await db.commit()

    # Dispatch AI risk evaluation in background
    background_tasks.add_task(evaluate_loan_risk, db_loan.id, db)
    return db_loan


@router.get("/", response_model=List[LoanApplicationResponse])
async def list_applications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, description="Search by applicant name"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List all loan applications with optional filtering."""
    q = select(LoanApplication).order_by(LoanApplication.created_at.desc())
    if status:
        q = q.where(LoanApplication.status == status)
    if search:
        q = q.where(LoanApplication.applicant_name.ilike(f"%{search}%"))
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/count")
async def count_by_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Return count of applications grouped by status."""
    result = await db.execute(
        select(LoanApplication.status, func.count(LoanApplication.id))
        .group_by(LoanApplication.status)
    )
    return {row[0]: row[1] for row in result.all()}


@router.get("/{application_id}", response_model=LoanApplicationResponse)
async def get_application(
    application_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single loan application by ID."""
    result = await db.execute(
        select(LoanApplication).where(LoanApplication.id == application_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return loan


@router.get("/{application_id}/details", response_model=LoanApplicationDetailResponse)
async def get_application_details(
    application_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Get full deep application details including KYC documents, audit trail, and disbursement."""
    result = await db.execute(
        select(LoanApplication)
        .where(LoanApplication.id == application_id)
        .options(
            selectinload(LoanApplication.documents),
            selectinload(LoanApplication.audit_log),
            selectinload(LoanApplication.disbursement),
        )
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return loan


@router.patch("/{application_id}/status", response_model=LoanApplicationResponse)
async def update_application_status(
    application_id: int,
    payload: LoanStatusUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Manually update loan status (officer override)."""
    result = await db.execute(
        select(LoanApplication).where(LoanApplication.id == application_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    old_status = loan.status
    loan.status = payload.status

    db.add(AuditLog(
        loan_id=loan.id,
        actor_id=current_user.id,
        action="STATUS_CHANGE",
        old_value=old_status,
        new_value=payload.status,
        notes=f"Manual override by {current_user.full_name}",
    ))

    await db.commit()
    await db.refresh(loan)
    return loan


@router.get("/{application_id}/audit", response_model=List[AuditLogResponse])
async def get_audit_log(
    application_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Get full audit trail for a loan application."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.loan_id == application_id)
        .order_by(AuditLog.timestamp.desc())
    )
    return result.scalars().all()
