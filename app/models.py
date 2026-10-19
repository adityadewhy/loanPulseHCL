"""
app/models.py — All SQLAlchemy ORM models for LoanMaster.
Single source of truth for database schema.
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ── Users (Loan Officers / Admins) ────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="OFFICER")  # ADMIN, OFFICER, VIEWER
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    assigned_loans = relationship("LoanApplication", back_populates="assigned_officer")
    audit_entries = relationship("AuditLog", back_populates="actor")


# ── Loan Applications ──────────────────────────────────────────────────────

class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id = Column(Integer, primary_key=True, index=True)

    # Applicant Info
    applicant_name = Column(String, index=True, nullable=False)
    applicant_email = Column(String, nullable=True)
    applicant_phone = Column(String, nullable=True)
    employment_type = Column(String, nullable=True)  # SALARIED, SELF_EMPLOYED, UNEMPLOYED

    # Financials
    annual_income = Column(Float, nullable=False)
    requested_amount = Column(Float, nullable=False)
    requested_term_months = Column(Integer, nullable=True, default=12)
    loan_purpose = Column(String, nullable=True)  # HOME, VEHICLE, EDUCATION, PERSONAL, BUSINESS

    # Lifecycle
    status = Column(String, default="PENDING", index=True)
    # PENDING → UNDER_REVIEW → APPROVED / REJECTED → DISBURSED → ACTIVE → CLOSED / DEFAULTED

    # AI Risk Assessment
    risk_score = Column(Integer, nullable=True)
    risk_reasoning = Column(Text, nullable=True)

    # Assignment
    assigned_officer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    assigned_officer = relationship("User", back_populates="assigned_loans")
    disbursement = relationship("Disbursement", back_populates="loan", uselist=False)
    repayment_schedule = relationship("RepaymentSchedule", back_populates="loan", order_by="RepaymentSchedule.installment_number")
    audit_log = relationship("AuditLog", back_populates="loan", order_by="AuditLog.timestamp.desc()")
    notifications = relationship("Notification", back_populates="loan")
    documents = relationship("LoanDocument", back_populates="loan", cascade="all, delete-orphan", order_by="LoanDocument.uploaded_at.desc()")


# ── Disbursements ──────────────────────────────────────────────────────────

class Disbursement(Base):
    __tablename__ = "disbursements"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loan_applications.id"), unique=True, nullable=False, index=True)

    disbursed_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)    # Annual % e.g. 12.5
    disbursement_date = Column(Date, nullable=False)
    payment_method = Column(String, default="BANK_TRANSFER")  # BANK_TRANSFER, CHEQUE, UPI
    bank_reference = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    loan = relationship("LoanApplication", back_populates="disbursement")


# ── Repayment Schedule ─────────────────────────────────────────────────────

class RepaymentSchedule(Base):
    __tablename__ = "repayment_schedule"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loan_applications.id"), nullable=False, index=True)

    installment_number = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    emi_amount = Column(Float, nullable=False)
    principal_component = Column(Float, nullable=False)
    interest_component = Column(Float, nullable=False)

    # Payment tracking
    status = Column(String, default="PENDING", index=True)  # PENDING, PAID, OVERDUE, WAIVED
    paid_date = Column(Date, nullable=True)
    paid_amount = Column(Float, nullable=True)
    penalty_amount = Column(Float, default=0.0)

    # Relationships
    loan = relationship("LoanApplication", back_populates="repayment_schedule")


# ── Audit Log ──────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loan_applications.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = system

    action = Column(String, nullable=False)   # STATUS_CHANGE, PAYMENT_RECORDED, AI_EVALUATED, etc.
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    loan = relationship("LoanApplication", back_populates="audit_log")
    actor = relationship("User", back_populates="audit_entries")


# ── Notifications ──────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_email = Column(String, nullable=False, index=True)
    loan_id = Column(Integer, ForeignKey("loan_applications.id"), nullable=True, index=True)

    type = Column(String, nullable=False)     # EMAIL, IN_APP
    event = Column(String, nullable=False)    # APPLICATION_RECEIVED, APPROVED, REJECTED, OVERDUE, etc.
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="PENDING")  # PENDING, SENT, FAILED

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    loan = relationship("LoanApplication", back_populates="notifications")


# ── Loan Documents (KYC & Financial Proof Attachments) ────────────────────

class LoanDocument(Base):
    __tablename__ = "loan_documents"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loan_applications.id"), nullable=False, index=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    document_type = Column(String, nullable=False)  # ID_PROOF, INCOME_PROOF, BANK_STATEMENT, COLLATERAL, OTHER
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    content_type = Column(String, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    loan = relationship("LoanApplication", back_populates="documents")
    uploaded_by = relationship("User")

