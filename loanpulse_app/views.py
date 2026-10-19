import csv
from html import escape
import json
import logging
import os
import re
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import FileResponse, HttpResponse
from django.templatetags.static import static
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.decorators import (api_view, permission_classes, throttle_classes,
                                       authentication_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .authentication import JWTAuthentication, issue_token
from .throttles import LoginThrottle, SignupThrottle, KarzaiThrottle, KycReviewThrottle
from .models import (AuditLog, Disbursement, LoanApplication, LoanDocument,
                     Notification, RepaymentSchedule, User)
from .serializers import (AuditSerializer, DisbursementCreateSerializer,
                          BorrowerLoanSerializer, DisbursementSerializer, DocumentSerializer,
                          LoanCreateSerializer, LoanSerializer, NotificationSerializer,
                          ScheduleSerializer, UserSerializer)
from .services import (add_notification, apply_assessment, assess_loan,
                      borrower_assessment_feedback, create_schedule,
                      deterministic_assessment, karzai_is_loan_query, karzai_reply,
                      money, review_kyc_document)

logger = logging.getLogger(__name__)
STAFF_ROLES = {"ADMIN", "OFFICER", "VIEWER"}
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024
ALLOWED_DOCUMENTS = {
    ".pdf": {"application/pdf"}, ".png": {"image/png"},
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"}, ".txt": {"text/plain"}, ".csv": {"text/csv", "application/vnd.ms-excel"},
}
SAFE_NAME = re.compile(r"[^\w.\-]")


def can_write(request):
    return request.user.role in {"ADMIN", "OFFICER"}


def is_borrower(request):
    return request.user.role == "CUSTOMER"


def visible_loans(request):
    if is_borrower(request):
        return LoanApplication.objects.filter(applicant_user=request.user)
    if request.user.role in STAFF_ROLES:
        return LoanApplication.objects.all()
    return LoanApplication.objects.none()


def visible_notifications(request):
    rows = Notification.objects.all()
    if is_borrower(request):
        rows = rows.filter(loan__applicant_user=request.user)
    elif request.user.role not in STAFF_ROLES:
        rows = rows.none()
    return rows


@require_GET
def frontend(request):
    page = (Path(settings.BASE_DIR) / "app" / "static" / "index.html").read_text()
    try:
        script_url = static("app.js")
        stylesheet_url = static("tailwind.css")
    except ValueError:
        script_url = "/static/app.js"
        stylesheet_url = "/static/tailwind.css"
    review_threshold = settings.LTI_REVIEW_THRESHOLD * 100
    rejection_threshold = settings.LTI_REJECTION_THRESHOLD * 100
    page = page.replace(
        "<body ",
        f'<body data-lti-review-threshold="{review_threshold:g}" data-lti-rejection-threshold="{rejection_threshold:g}" data-boss-email="{escape(settings.BOSS_EMAIL, quote=True)}" ',
        1,
    )
    page = page.replace("above 60% is rejected by current policy", f"above {rejection_threshold:g}% is rejected by current policy")
    page = page.replace('href="/static/tailwind.css"', f'href="{stylesheet_url}"')
    page = page.replace('src="/static/app.js"', f'src="{script_url}"')
    return HttpResponse(page, content_type="text/html; charset=utf-8")


@require_GET
def health(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return HttpResponse('{"status":"healthy","database":"ok"}', content_type="application/json")
    except Exception:
        logger.exception("Health check database query failed")
        return HttpResponse('{"status":"degraded","database":"error"}', content_type="application/json", status=503)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login(request):
    """Exchange a user account's credentials for a short-lived bearer token."""
    email = str(request.data.get("username") or request.data.get("email") or "").strip().lower()
    password = str(request.data.get("password") or "")
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    try:
        valid = bool(user and check_password(password, user.hashed_password))
    except ValueError:
        valid = False
    if user and not valid and user.hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            valid = bcrypt.checkpw(password.encode(), user.hashed_password.encode())
        except (ImportError, ValueError):
            valid = False
    if not valid:
        return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
    return Response({"access_token": issue_token(user), "token_type": "bearer"})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([SignupThrottle])
def signup(request):
    """Create a borrower account or submit a staff registration for boss review."""
    email = str(request.data.get("email", "")).strip().lower()
    full_name = str(request.data.get("full_name", "")).strip()
    password = str(request.data.get("password", ""))
    account_type = str(request.data.get("account_type", "BORROWER")).upper()
    if account_type not in {"BORROWER", "STAFF"}:
        return Response({"detail": "Choose borrower or staff registration."}, status=status.HTTP_400_BAD_REQUEST)
    if not email or len(email) > 100 or not 2 <= len(full_name) <= 100 or not 12 <= len(password) <= 128:
        return Response({"detail": "Enter a valid email, a name between 2 and 100 characters, and a password between 12 and 128 characters."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_email(email)
    except ValidationError:
        return Response({"detail": "Provide a valid email address."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_password(password, User(email=email, full_name=full_name))
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(email__iexact=email).exists():
        return Response({"detail": "An account with this email already exists."}, status=status.HTTP_409_CONFLICT)
    try:
        staff_signup = account_type == "STAFF"
        user = User.objects.create(
            email=email, full_name=full_name,
            role="OFFICER" if staff_signup else "CUSTOMER",
            hashed_password=make_password(password), is_active=not staff_signup,
            staff_registration_status="PENDING" if staff_signup else "NONE",
        )
    except IntegrityError:
        return Response({"detail": "An account with this email already exists."}, status=status.HTTP_409_CONFLICT)
    if account_type == "STAFF":
        return Response({"detail": "Staff registration submitted. You can sign in after the boss approves it.", "staff_registration_status": "PENDING"}, status=status.HTTP_201_CREATED)
    return Response({
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": UserSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
def staff_registrations(request):
    if request.user.role != "ADMIN" or not settings.BOSS_EMAIL or request.user.email.lower() != settings.BOSS_EMAIL:
        return Response({"detail": "Boss administrator access required."}, status=status.HTTP_403_FORBIDDEN)
    if request.method == "GET":
        state = str(request.query_params.get("status", "PENDING")).upper()
        if state not in {"PENDING", "APPROVED", "DISAPPROVED"}:
            return Response({"detail": "Invalid staff registration status."}, status=status.HTTP_400_BAD_REQUEST)
        rows = User.objects.filter(staff_registration_status=state).order_by("created_at")
        return Response([{"id": user.id, "email": user.email, "full_name": user.full_name, "status": user.staff_registration_status, "created_at": user.created_at} for user in rows])

    try:
        user_id = int(request.data.get("user_id"))
    except (TypeError, ValueError):
        return Response({"detail": "A valid user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    next_state = str(request.data.get("status", "")).upper()
    if next_state not in {"PENDING", "APPROVED", "DISAPPROVED"}:
        return Response({"detail": "Status must be pending, approved, or disapproved."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(id=user_id)
            if user.role != "OFFICER" or user.staff_registration_status == "NONE":
                return Response({"detail": "Staff registration not found."}, status=status.HTTP_404_NOT_FOUND)
            user.staff_registration_status = next_state
            user.is_active = next_state == "APPROVED"
            user.save(update_fields=["staff_registration_status", "is_active"])
    except User.DoesNotExist:
        return Response({"detail": "Staff registration not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"id": user.id, "status": user.staff_registration_status, "is_active": user.is_active})


@api_view(["GET"])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["GET", "POST"])
def applications(request):
    if request.method == "GET":
        rows = visible_loans(request)
        state = request.query_params.get("status")
        search = request.query_params.get("search", "").strip()
        if state:
            rows = rows.filter(status=state.upper())
        if search:
            rows = rows.filter(applicant_name__icontains=search)
        try:
            skip = max(0, int(request.query_params.get("skip", 0)))
            limit = min(100, max(1, int(request.query_params.get("limit", 20))))
        except ValueError:
            return Response({"detail": "skip and limit must be integers."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = BorrowerLoanSerializer if is_borrower(request) else LoanSerializer
        return Response(serializer(rows[skip:skip + limit], many=True).data)

    if not can_write(request) and not is_borrower(request):
        return Response({"detail": "Loan application access required."}, status=status.HTTP_403_FORBIDDEN)
    payload = request.data.copy()
    if is_borrower(request):
        # The authenticated account is the source of borrower identity fields.
        payload["applicant_name"] = request.user.full_name
        payload["applicant_email"] = request.user.email
    serializer = LoanCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        loan_fields = dict(serializer.validated_data)
        if is_borrower(request):
            loan_fields["applicant_user"] = request.user
            loan = LoanApplication.objects.create(**loan_fields, assigned_officer=None)
        else:
            loan = LoanApplication.objects.create(**loan_fields, assigned_officer=request.user)
        AuditLog.objects.create(loan=loan, actor=request.user, action="APPLICATION_SUBMITTED", new_value="PENDING", notes=f"Submitted by {request.user.full_name}")
    # Do not hold a database transaction open while external inference runs.
    try:
        assessment, provider = assess_loan(loan)
    except Exception:
        logger.exception("Loan risk assessment failed; using deterministic assessment")
        assessment, provider = deterministic_assessment(loan), "rules"
    with transaction.atomic():
        loan = LoanApplication.objects.select_for_update().get(pk=loan.pk)
        apply_assessment(loan, assessment, provider)
        add_notification(loan, "APPLICATION_RECEIVED", f"Loan application #{loan.pk} received", "Your application was received and is being assessed.")
    if is_borrower(request):
        result = BorrowerLoanSerializer(loan).data
        result["borrower_feedback"] = borrower_assessment_feedback(loan, assessment, provider)
    else:
        result = LoanSerializer(loan).data
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@throttle_classes([KarzaiThrottle])
def karzai_chat(request):
    if not is_borrower(request):
        return Response({"detail": "KARZai is available to borrower accounts."}, status=status.HTTP_403_FORBIDDEN)
    question = str(request.data.get("question", "")).strip()
    if not question or len(question) > 280:
        return Response({"detail": "Enter a question of up to 280 characters."}, status=status.HTTP_400_BAD_REQUEST)
    if not karzai_is_loan_query(question):
        return Response({"answer": "I can help with LoanPulse applications, loan terms, required documents, and repayment questions."})
    return Response({"answer": karzai_reply(question)})


@api_view(["POST"])
@throttle_classes([KycReviewThrottle])
def karzai_kyc_review(request, document_id):
    if not is_borrower(request):
        return Response({"detail": "Borrower access required."}, status=status.HTTP_403_FORBIDDEN)
    if request.data.get("consent") is not True:
        return Response({"detail": "Consent is required before sending this document to Gemini for review."}, status=status.HTTP_400_BAD_REQUEST)
    document = get_object_or_404(LoanDocument.objects.filter(loan__applicant_user=request.user), pk=document_id)
    try:
        return Response(review_kyc_document(document))
    except (ValueError, FileNotFoundError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except RuntimeError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as exc:
        logger.warning("KARZai KYC review failed (%s)", type(exc).__name__)
        return Response({"detail": "AI document review failed. Your uploaded document is unchanged; please try later."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
def application_count(request):
    grouped = visible_loans(request).values("status").annotate(count=Count("id"))
    return Response({row["status"].lower(): row["count"] for row in grouped})


@api_view(["GET"])
def application_details(request, loan_id):
    loan = get_object_or_404(visible_loans(request).select_related("disbursement"), pk=loan_id)
    if is_borrower(request):
        data = BorrowerLoanSerializer(loan).data
        data["documents"] = DocumentSerializer(loan.documents.all(), many=True).data
        data["schedule"] = ScheduleSerializer(loan.repayment_schedule.all(), many=True).data
        data["status_history"] = [
            {"status": row.new_value, "timestamp": row.timestamp}
            for row in loan.audit_log.filter(action__in=["APPLICATION_SUBMITTED", "AI_EVALUATED", "STATUS_CHANGE"]).order_by("timestamp")
        ]
        return Response(data)
    data = LoanSerializer(loan).data
    data["disbursement"] = DisbursementSerializer(loan.disbursement).data if hasattr(loan, "disbursement") else None
    data["documents"] = DocumentSerializer(loan.documents.all(), many=True).data
    data["audit_log"] = AuditSerializer(loan.audit_log.select_related("actor"), many=True).data
    return Response(data)


@api_view(["PATCH"])
def application_status(request, loan_id):
    if not can_write(request):
        return Response({"detail": "Loan officer access required."}, status=status.HTTP_403_FORBIDDEN)
    with transaction.atomic():
        loan = get_object_or_404(LoanApplication.objects.select_for_update(), pk=loan_id)
        new_status = str(request.data.get("status", "")).upper()
        allowed = {
            "PENDING": {"UNDER_REVIEW", "APPROVED", "REJECTED"},
            "UNDER_REVIEW": {"APPROVED", "REJECTED"},
            "APPROVED": {"REJECTED"},
            "REJECTED": set(), "DISBURSED": set(), "ACTIVE": set(), "CLOSED": set(), "DEFAULTED": set(),
        }
        if new_status not in allowed.get(loan.status, set()):
            return Response({"detail": f"Cannot change status from {loan.status} to {new_status or 'empty'}."}, status=status.HTTP_400_BAD_REQUEST)
        old = loan.status
        loan.status = new_status
        loan.updated_at = timezone.now()
        loan.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(loan=loan, actor=request.user, action="STATUS_CHANGE", old_value=old, new_value=new_status, notes=f"Changed by {request.user.full_name}")
        add_notification(loan, f"APPLICATION_{new_status}", f"Loan application #{loan.pk} {new_status.lower()}", f"Your application status is now {new_status}.")
        return Response(LoanSerializer(loan).data)


@api_view(["GET"])
def application_audit(request, loan_id):
    loan = get_object_or_404(visible_loans(request), pk=loan_id)
    if is_borrower(request):
        rows = loan.audit_log.filter(action__in=["APPLICATION_SUBMITTED", "AI_EVALUATED", "STATUS_CHANGE"])
        return Response([{"status": row.new_value, "timestamp": row.timestamp} for row in rows.order_by("timestamp")])
    return Response(AuditSerializer(loan.audit_log.select_related("actor"), many=True).data)


@api_view(["GET", "POST"])
def disbursements(request):
    if request.method == "GET":
        rows = Disbursement.objects.select_related("loan")
        if is_borrower(request):
            rows = rows.filter(loan__applicant_user=request.user)
        elif request.user.role not in STAFF_ROLES:
            rows = rows.none()
        return Response(DisbursementSerializer(rows, many=True).data)
    if not can_write(request):
        return Response({"detail": "Loan officer access required."}, status=status.HTTP_403_FORBIDDEN)
    serializer = DisbursementCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        loan = get_object_or_404(LoanApplication.objects.select_for_update(), pk=data["loan_id"])
        if Disbursement.objects.filter(loan=loan).exists():
            return Response({"detail": "Loan has already been disbursed."}, status=status.HTTP_409_CONFLICT)
        if loan.status != "APPROVED":
            return Response({"detail": f"Loan must be APPROVED before disbursement; current status is {loan.status}."}, status=status.HTTP_400_BAD_REQUEST)
        disbursement = Disbursement.objects.create(loan=loan, disbursed_amount=data["disbursed_amount"], interest_rate=data["interest_rate"], disbursement_date=data["disbursement_date"], payment_method=data["payment_method"], bank_reference=data.get("bank_reference") or None)
        schedule = create_schedule(loan, disbursement)
        old = loan.status
        loan.status = "DISBURSED"
        loan.updated_at = timezone.now()
        loan.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(loan=loan, actor=request.user, action="LOAN_DISBURSED", old_value=old, new_value="DISBURSED", notes=f"Disbursed {disbursement.disbursed_amount} at {disbursement.interest_rate}%.")
        first = schedule[0]
        add_notification(loan, "LOAN_DISBURSED", f"Loan #{loan.pk} disbursed", f"Your loan has been disbursed. Monthly instalment: {first['emi_amount']}. First due date: {first['due_date']}.")
    return Response(DisbursementSerializer(disbursement).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def disbursement_detail(request, loan_id):
    get_object_or_404(visible_loans(request), pk=loan_id)
    obj = get_object_or_404(Disbursement, loan_id=loan_id)
    return Response(DisbursementSerializer(obj).data)


@api_view(["GET"])
def dashboard(request):
    loans = visible_loans(request)
    grouped = loans.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in grouped}
    schedules = RepaymentSchedule.objects.filter(loan__in=loans)
    total_paid_due = schedules.filter(status="PAID").count()
    overdue = schedules.filter(status="OVERDUE").count()
    denominator = total_paid_due + overdue
    return Response({
        "total_applications": sum(counts.values()),
        **{key.lower(): counts.get(key, 0) for key in ["PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED", "DISBURSED", "ACTIVE", "CLOSED", "DEFAULTED"]},
        "total_disbursed_amount": Disbursement.objects.filter(loan__in=loans).aggregate(total=Sum("disbursed_amount"))["total"] or 0,
        "total_overdue_installments": overdue,
        "collection_rate": round(100 * total_paid_due / denominator, 1) if denominator else 100.0,
    })


@api_view(["GET"])
def repayment_schedule(request, loan_id):
    loan = get_object_or_404(visible_loans(request), pk=loan_id)
    rows = list(loan.repayment_schedule.all())
    paid = sum((row.paid_amount or Decimal(0) for row in rows), Decimal(0))
    total_emi = sum((row.emi_amount for row in rows), Decimal(0))
    return Response({
        "loan_id": loan_id, "total_installments": len(rows),
        "paid_count": sum(row.status == "PAID" for row in rows),
        "overdue_count": sum(row.status == "OVERDUE" for row in rows),
        "pending_count": sum(row.status == "PENDING" for row in rows),
        "total_emi": money(total_emi), "total_paid": money(paid),
        "outstanding_balance": money(max(Decimal(0), total_emi - paid)),
        "schedule": ScheduleSerializer(rows, many=True).data,
    })


@api_view(["POST"])
def record_payment(request, loan_id, installment_id):
    if not can_write(request):
        return Response({"detail": "Loan officer access required."}, status=status.HTTP_403_FORBIDDEN)
    amount = request.data.get("paid_amount")
    try:
        amount = money(amount)
        if amount <= 0:
            raise ValueError
        paid_date = date.fromisoformat(request.data["paid_date"]) if request.data.get("paid_date") else date.today()
    except (ValueError, TypeError, KeyError):
        return Response({"detail": "Provide a positive paid_amount and a valid optional paid_date."}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        loan = get_object_or_404(LoanApplication.objects.select_for_update(), pk=loan_id)
        installment = get_object_or_404(RepaymentSchedule.objects.select_for_update(), pk=installment_id, loan=loan)
        if installment.status == "PAID":
            return Response({"detail": "Installment is already fully paid."}, status=status.HTTP_400_BAD_REQUEST)
        received = money((installment.paid_amount or Decimal(0)) + amount)
        installment.paid_amount = received
        installment.paid_date = paid_date
        target = money(installment.emi_amount + installment.penalty_amount)
        if received >= target:
            installment.status = "PAID"
        installment.save(update_fields=["paid_amount", "paid_date", "status"])
        if loan.status == "DISBURSED":
            loan.status = "ACTIVE"
        if not loan.repayment_schedule.exclude(status="PAID").exists():
            loan.status = "CLOSED"
        loan.updated_at = timezone.now()
        loan.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(loan=loan, actor=request.user, action="PAYMENT_RECORDED", old_value="UNPAID", new_value=installment.status, notes=f"Received {amount} for instalment {installment.installment_number}.")
        add_notification(loan, "PAYMENT_CONFIRMATION", f"Payment received for loan #{loan.pk}", f"Payment of {amount} was received for instalment {installment.installment_number}.")
    return Response(ScheduleSerializer(installment).data)


@api_view(["GET"])
def overdue_installments(request):
    rows = RepaymentSchedule.objects.filter(status="OVERDUE").select_related("loan")
    if is_borrower(request):
        rows = rows.filter(loan__applicant_user=request.user)
    elif request.user.role not in STAFF_ROLES:
        rows = rows.none()
    return Response(ScheduleSerializer(rows, many=True).data)


@api_view(["POST"])
def trigger_overdue_check(request):
    if request.user.role not in {"ADMIN", "OFFICER"}:
        return Response({"detail": "Loan officer access required."}, status=status.HTTP_403_FORBIDDEN)
    today = date.today()
    count = 0
    with transaction.atomic():
        rows = RepaymentSchedule.objects.select_for_update().filter(status="PENDING", due_date__lt=today)
        for row in rows:
            row.status = "OVERDUE"
            row.save(update_fields=["status"])
            AuditLog.objects.create(loan=row.loan, action="INSTALLMENT_OVERDUE", old_value="PENDING", new_value="OVERDUE", notes="Installment marked overdue; no penalty was assessed automatically.")
            add_notification(row.loan, "INSTALLMENT_OVERDUE", f"Loan #{row.loan_id} payment overdue", f"Installment {row.installment_number} is overdue. Contact the loan officer for next steps.")
            count += 1
    return Response({"status": "success", "overdue_check": {"marked_overdue": count}})


@api_view(["GET"])
def export_schedule(request, loan_id):
    loan = get_object_or_404(visible_loans(request), pk=loan_id)
    rows = loan.repayment_schedule.all()
    if not rows.exists():
        return Response({"detail": "No repayment schedule exists for this loan."}, status=status.HTTP_404_NOT_FOUND)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="loan_{loan.pk}_schedule.csv"'
    writer = csv.writer(response)
    writer.writerow(["Installment Number", "Due Date", "EMI", "Principal", "Interest", "Penalty", "Status", "Paid Date", "Paid Amount"])
    for row in rows:
        writer.writerow([row.installment_number, row.due_date.isoformat(), row.emi_amount, row.principal_component, row.interest_component, row.penalty_amount, row.status, row.paid_date or "", row.paid_amount if row.paid_amount is not None else ""])
    return response


@api_view(["GET"])
def notifications(request):
    rows = visible_notifications(request)
    loan_id = request.query_params.get("loan_id")
    if loan_id:
        rows = rows.filter(loan_id=loan_id)
    if request.query_params.get("unread_only", "false").lower() == "true":
        rows = rows.filter(read_at__isnull=True)
    try:
        limit = min(100, max(1, int(request.query_params.get("limit", 50))))
    except ValueError:
        return Response({"detail": "limit must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(NotificationSerializer(rows[:limit], many=True).data)


@api_view(["GET"])
def unread_count(request):
    return Response({"unread_count": visible_notifications(request).filter(read_at__isnull=True).count()})


@api_view(["PATCH"])
def mark_notification_read(request, notification_id):
    obj = get_object_or_404(visible_notifications(request), pk=notification_id)
    if obj.read_at is None:
        obj.read_at = timezone.now()
        obj.save(update_fields=["read_at"])
    return Response(NotificationSerializer(obj).data)


@api_view(["GET", "POST"])
def loan_documents(request, loan_id):
    loan = get_object_or_404(visible_loans(request), pk=loan_id)
    if request.method == "GET":
        return Response(DocumentSerializer(loan.documents.all(), many=True).data)
    if not can_write(request) and not is_borrower(request):
        return Response({"detail": "Loan officer access required."}, status=status.HTTP_403_FORBIDDEN)
    uploaded = request.FILES.get("file")
    kind = str(request.data.get("document_type", "OTHER")).upper()
    if not uploaded or kind not in {"ID_PROOF", "INCOME_PROOF", "BANK_STATEMENT", "COLLATERAL", "OTHER"}:
        return Response({"detail": "Provide a supported document and document_type."}, status=status.HTTP_400_BAD_REQUEST)
    extension = Path(uploaded.name or "").suffix.lower()
    allowed_mimes = ALLOWED_DOCUMENTS.get(extension)
    if not allowed_mimes or uploaded.content_type not in allowed_mimes:
        return Response({"detail": "Unsupported document type."}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded.size > MAX_DOCUMENT_SIZE:
        return Response({"detail": "File size exceeds the 15 MB limit."}, status=status.HTTP_400_BAD_REQUEST)
    safe_name = SAFE_NAME.sub("_", Path(uploaded.name).name)[:180] or "document"
    relative = Path(str(loan.pk)) / f"{uuid.uuid4().hex}_{safe_name}"
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        return Response({"detail": "Invalid file path."}, status=status.HTTP_400_BAD_REQUEST)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as output:
            for chunk in uploaded.chunks():
                output.write(chunk)
        with transaction.atomic():
            obj = LoanDocument.objects.create(loan=loan, uploaded_by=request.user, document_type=kind, file_name=safe_name, file_path=str(target), file_size_bytes=uploaded.size, content_type=uploaded.content_type)
            AuditLog.objects.create(loan=loan, actor=request.user, action="DOCUMENT_ATTACHED", notes=f"Attached {kind} ({safe_name}).")
    except Exception:
        target.unlink(missing_ok=True)
        logger.exception("Document upload failed for loan %s", loan.pk)
        return Response({"detail": "Document upload failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(DocumentSerializer(obj).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def document_download(request, document_id):
    rows = LoanDocument.objects.all()
    if is_borrower(request):
        rows = rows.filter(loan__applicant_user=request.user)
    elif request.user.role not in STAFF_ROLES:
        rows = rows.none()
    obj = get_object_or_404(rows, pk=document_id)
    path = Path(obj.file_path).resolve()
    root = Path(settings.MEDIA_ROOT).resolve()
    if root not in path.parents or not path.is_file():
        return Response({"detail": "Document file is unavailable."}, status=status.HTTP_404_NOT_FOUND)
    return FileResponse(path.open("rb"), as_attachment=True, filename=obj.file_name, content_type=obj.content_type or "application/octet-stream")


@api_view(["DELETE"])
def document_delete(request, document_id):
    if not can_write(request):
        return Response({"detail": "Loan officer access required."}, status=status.HTTP_403_FORBIDDEN)
    obj = get_object_or_404(LoanDocument, pk=document_id)
    path = Path(obj.file_path).resolve()
    root = Path(settings.MEDIA_ROOT).resolve()
    if root not in path.parents:
        return Response({"detail": "Invalid document path."}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        loan = obj.loan
        AuditLog.objects.create(loan=loan, actor=request.user, action="DOCUMENT_DELETED", notes=f"Removed document: {obj.file_name}")
        obj.delete()
        path.unlink(missing_ok=True)
    return Response(status=status.HTTP_204_NO_CONTENT)
