from decimal import Decimal
from rest_framework import serializers
from .models import (
    AuditLog, Disbursement, LoanApplication, LoanDocument, Notification,
    RepaymentSchedule, User,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_active", "created_at"]


class LoanSerializer(serializers.ModelSerializer):
    assigned_officer_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = LoanApplication
        fields = ["id", "applicant_name", "applicant_email", "applicant_phone", "employment_type", "annual_income", "requested_amount", "requested_term_months", "loan_purpose", "status", "risk_score", "risk_reasoning", "assigned_officer_id", "created_at", "updated_at"]


class BorrowerLoanSerializer(serializers.ModelSerializer):
    """Expose only the applicant's own loan details, never internal underwriting notes."""
    class Meta:
        model = LoanApplication
        fields = ["id", "requested_amount", "requested_term_months", "loan_purpose", "status", "created_at", "updated_at"]


class DisbursementSerializer(serializers.ModelSerializer):
    loan_id = serializers.IntegerField(read_only=True)
    class Meta:
        model = Disbursement
        fields = ["id", "loan_id", "disbursed_amount", "interest_rate", "disbursement_date", "payment_method", "bank_reference", "created_at"]


class ScheduleSerializer(serializers.ModelSerializer):
    loan_id = serializers.IntegerField(read_only=True)
    class Meta:
        model = RepaymentSchedule
        fields = ["id", "loan_id", "installment_number", "due_date", "emi_amount", "principal_component", "interest_component", "status", "paid_date", "paid_amount", "penalty_amount"]


class AuditSerializer(serializers.ModelSerializer):
    loan_id = serializers.IntegerField(read_only=True)
    actor_id = serializers.IntegerField(read_only=True, allow_null=True)
    class Meta:
        model = AuditLog
        fields = ["id", "loan_id", "actor_id", "action", "old_value", "new_value", "notes", "timestamp"]


class NotificationSerializer(serializers.ModelSerializer):
    loan_id = serializers.IntegerField(read_only=True, allow_null=True)
    class Meta:
        model = Notification
        fields = ["id", "recipient_email", "loan_id", "type", "event", "subject", "body", "sent_at", "read_at", "status", "created_at"]


class DocumentSerializer(serializers.ModelSerializer):
    loan_id = serializers.IntegerField(read_only=True)
    uploaded_by_id = serializers.IntegerField(read_only=True, allow_null=True)
    class Meta:
        model = LoanDocument
        fields = ["id", "loan_id", "uploaded_by_id", "document_type", "file_name", "file_size_bytes", "content_type", "uploaded_at"]


class LoanCreateSerializer(serializers.Serializer):
    applicant_name = serializers.CharField(min_length=2, max_length=100)
    applicant_email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    applicant_phone = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=100)
    employment_type = serializers.ChoiceField(["SALARIED", "SELF_EMPLOYED", "UNEMPLOYED"], required=False, allow_null=True)
    annual_income = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    requested_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    requested_term_months = serializers.IntegerField(min_value=1, max_value=360, default=12)
    loan_purpose = serializers.ChoiceField(["HOME", "VEHICLE", "EDUCATION", "PERSONAL", "BUSINESS"], required=False, allow_null=True)


class DisbursementCreateSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField(min_value=1)
    disbursed_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    interest_rate = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=0, max_value=100)
    disbursement_date = serializers.DateField()
    payment_method = serializers.ChoiceField(["BANK_TRANSFER", "CHEQUE", "UPI"], default="BANK_TRANSFER")
    bank_reference = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
