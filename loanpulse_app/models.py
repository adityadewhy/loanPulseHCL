from django.db import models
from django.utils import timezone


class User(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(max_length=100, unique=True)
    hashed_password = models.CharField(max_length=255)
    full_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, default="OFFICER")
    is_active = models.BooleanField(default=True)
    staff_registration_status = models.CharField(max_length=20, default="NONE")
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def is_authenticated(self):
        return True

    class Meta:
        db_table = "users"


class LoanApplication(models.Model):
    id = models.AutoField(primary_key=True)
    applicant_name = models.CharField(max_length=100)
    applicant_email = models.EmailField(max_length=254, null=True, blank=True)
    applicant_phone = models.CharField(max_length=100, null=True, blank=True)
    employment_type = models.CharField(max_length=32, null=True, blank=True)
    annual_income = models.DecimalField(max_digits=14, decimal_places=2)
    requested_amount = models.DecimalField(max_digits=14, decimal_places=2)
    requested_term_months = models.IntegerField(default=12, null=True, blank=True)
    loan_purpose = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=32, default="PENDING", db_index=True)
    risk_score = models.IntegerField(null=True, blank=True)
    risk_reasoning = models.TextField(null=True, blank=True)
    applicant_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="applicant_user_id", related_name="loan_applications")
    assigned_officer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="assigned_officer_id", related_name="assigned_loans")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "loan_applications"
        ordering = ["-created_at"]


class Disbursement(models.Model):
    id = models.AutoField(primary_key=True)
    loan = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, db_column="loan_id", related_name="disbursement")
    disbursed_amount = models.DecimalField(max_digits=14, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=7, decimal_places=4)
    disbursement_date = models.DateField()
    payment_method = models.CharField(max_length=32, default="BANK_TRANSFER")
    bank_reference = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "disbursements"
        ordering = ["-created_at"]


class RepaymentSchedule(models.Model):
    id = models.AutoField(primary_key=True)
    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, db_column="loan_id", related_name="repayment_schedule")
    installment_number = models.IntegerField()
    due_date = models.DateField(db_index=True)
    emi_amount = models.DecimalField(max_digits=14, decimal_places=2)
    principal_component = models.DecimalField(max_digits=14, decimal_places=2)
    interest_component = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, default="PENDING", db_index=True)
    paid_date = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    penalty_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "repayment_schedule"
        ordering = ["installment_number"]
        constraints = [models.UniqueConstraint(fields=["loan", "installment_number"], name="uniq_loan_installment")]


class AuditLog(models.Model):
    id = models.AutoField(primary_key=True)
    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, db_column="loan_id", related_name="audit_log")
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="actor_id", related_name="audit_entries")
    action = models.CharField(max_length=100)
    old_value = models.CharField(max_length=255, null=True, blank=True)
    new_value = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-timestamp"]


class Notification(models.Model):
    id = models.AutoField(primary_key=True)
    recipient_email = models.EmailField(max_length=254, db_index=True)
    loan = models.ForeignKey(LoanApplication, null=True, blank=True, on_delete=models.SET_NULL, db_column="loan_id", related_name="notifications")
    type = models.CharField(max_length=32)
    event = models.CharField(max_length=64)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="PENDING")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]


class LoanDocument(models.Model):
    id = models.AutoField(primary_key=True)
    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, db_column="loan_id", related_name="documents")
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, db_column="uploaded_by_id", related_name="uploaded_documents")
    document_type = models.CharField(max_length=40)
    file_name = models.CharField(max_length=255)
    file_path = models.TextField()
    file_size_bytes = models.IntegerField()
    content_type = models.CharField(max_length=255, null=True, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "loan_documents"
        ordering = ["-uploaded_at"]
