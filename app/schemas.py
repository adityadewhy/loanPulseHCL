"""
app/schemas.py — All Pydantic v2 schemas (request/response contracts).
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, date


# ── Auth / Users ───────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: str = Field(default="OFFICER", pattern="^(ADMIN|OFFICER|VIEWER)$")

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: str
    password: str


# ── Loan Applications ──────────────────────────────────────────────────────

class LoanApplicationBase(BaseModel):
    applicant_name: str = Field(..., min_length=2, max_length=100)
    applicant_email: Optional[str] = None
    applicant_phone: Optional[str] = None
    employment_type: Optional[str] = Field(default=None, pattern="^(SALARIED|SELF_EMPLOYED|UNEMPLOYED)?$")
    annual_income: float = Field(..., gt=0)
    requested_amount: float = Field(..., gt=0)
    requested_term_months: Optional[int] = Field(default=12, ge=1, le=360)
    loan_purpose: Optional[str] = Field(default=None, pattern="^(HOME|VEHICLE|EDUCATION|PERSONAL|BUSINESS)?$")

class LoanApplicationCreate(LoanApplicationBase):
    pass

class LoanStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(PENDING|UNDER_REVIEW|APPROVED|REJECTED|DISBURSED|ACTIVE|CLOSED|DEFAULTED)$")

class LoanApplicationResponse(LoanApplicationBase):
    id: int
    status: str
    risk_score: Optional[int] = None
    risk_reasoning: Optional[str] = None
    assigned_officer_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class LoanApplicationDetail(LoanApplicationResponse):
    """Full detail view — includes nested disbursement."""
    disbursement: Optional["DisbursementResponse"] = None
    model_config = ConfigDict(from_attributes=True)


# ── Disbursements ──────────────────────────────────────────────────────────

class DisbursementCreate(BaseModel):
    loan_id: int
    disbursed_amount: float = Field(..., gt=0)
    interest_rate: float = Field(..., gt=0, le=100, description="Annual interest rate %")
    disbursement_date: date
    payment_method: str = Field(default="BANK_TRANSFER", pattern="^(BANK_TRANSFER|CHEQUE|UPI)$")
    bank_reference: Optional[str] = None

class DisbursementResponse(BaseModel):
    id: int
    loan_id: int
    disbursed_amount: float
    interest_rate: float
    disbursement_date: date
    payment_method: str
    bank_reference: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Repayment Schedule ─────────────────────────────────────────────────────

class RepaymentScheduleResponse(BaseModel):
    id: int
    loan_id: int
    installment_number: int
    due_date: date
    emi_amount: float
    principal_component: float
    interest_component: float
    status: str
    paid_date: Optional[date] = None
    paid_amount: Optional[float] = None
    penalty_amount: float
    model_config = ConfigDict(from_attributes=True)

class RecordPaymentRequest(BaseModel):
    paid_amount: float = Field(..., gt=0)
    paid_date: Optional[date] = None  # defaults to today

class RepaymentSummary(BaseModel):
    loan_id: int
    total_installments: int
    paid_count: int
    overdue_count: int
    pending_count: int
    total_emi: float
    total_paid: float
    outstanding_balance: float
    schedule: List[RepaymentScheduleResponse]


# ── Audit Log ──────────────────────────────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: int
    loan_id: int
    actor_id: Optional[int] = None
    action: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Notifications ──────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: int
    recipient_email: str
    loan_id: Optional[int] = None
    type: str
    event: str
    subject: str
    body: str
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Dashboard KPIs ─────────────────────────────────────────────────────────

class DashboardKPIs(BaseModel):
    total_applications: int
    pending: int
    under_review: int
    approved: int
    rejected: int
    disbursed: int
    active: int
    closed: int
    defaulted: int
    total_disbursed_amount: float
    total_overdue_installments: int
    collection_rate: float  # % of due payments that are PAID


# ── Loan Documents ─────────────────────────────────────────────────────────

class LoanDocumentResponse(BaseModel):
    id: int
    loan_id: int
    uploaded_by_id: Optional[int] = None
    document_type: str
    file_name: str
    file_path: str
    file_size_bytes: int
    content_type: Optional[str] = None
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LoanApplicationDetailResponse(LoanApplicationResponse):
    documents: List[LoanDocumentResponse] = []
    audit_log: List[AuditLogResponse] = []
    disbursement: Optional[DisbursementResponse] = None