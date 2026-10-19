"""
app/routers/dashboard.py — Executive KPIs and portfolio summary metrics.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_async_db
from app.models import LoanApplication, Disbursement, RepaymentSchedule, User
from app.schemas import DashboardKPIs
from app.auth.utils import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis", response_model=DashboardKPIs)
async def get_kpis(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns executive metrics for the loan portfolio:
    - Status counts
    - Total capital disbursed
    - Total overdue installments
    - Collection rate %
    """
    # 1. Status breakdown
    status_counts_res = await db.execute(
        select(LoanApplication.status, func.count(LoanApplication.id))
        .group_by(LoanApplication.status)
    )
    counts = {s: c for s, c in status_counts_res.all()}

    total_apps = sum(counts.values())

    # 2. Total disbursed capital
    disb_res = await db.execute(select(func.sum(Disbursement.disbursed_amount)))
    total_disbursed = disb_res.scalar() or 0.0

    # 3. Total overdue installments
    overdue_res = await db.execute(
        select(func.count(RepaymentSchedule.id))
        .where(RepaymentSchedule.status == "OVERDUE")
    )
    total_overdue = overdue_res.scalar() or 0

    # 4. Collection rate: paid installments / (paid + overdue)
    paid_res = await db.execute(
        select(func.count(RepaymentSchedule.id))
        .where(RepaymentSchedule.status == "PAID")
    )
    paid_count = paid_res.scalar() or 0

    due_total = paid_count + total_overdue
    collection_rate = round((paid_count / due_total * 100.0), 1) if due_total > 0 else 100.0

    return DashboardKPIs(
        total_applications=total_apps,
        pending=counts.get("PENDING", 0),
        under_review=counts.get("UNDER_REVIEW", 0),
        approved=counts.get("APPROVED", 0),
        rejected=counts.get("REJECTED", 0),
        disbursed=counts.get("DISBURSED", 0),
        active=counts.get("ACTIVE", 0),
        closed=counts.get("CLOSED", 0),
        defaulted=counts.get("DEFAULTED", 0),
        total_disbursed_amount=round(float(total_disbursed), 2),
        total_overdue_installments=total_overdue,
        collection_rate=collection_rate,
    )
