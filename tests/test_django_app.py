from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from loanpulse_app.authentication import issue_token
from loanpulse_app.models import Disbursement, LoanApplication, LoanDocument, Notification, RepaymentSchedule, User
from loanpulse_app.services import (
    _extract_assessment, assess_loan, calculate_emi, deterministic_assessment,
    generate_schedule, karzai_is_loan_query, karzai_reply, review_kyc_document,
)


def fake_loan(amount="10000", income="50000", term=12):
    return SimpleNamespace(
        requested_amount=Decimal(amount), annual_income=Decimal(income),
        requested_term_months=term, applicant_name="Test Applicant",
    )


def test_lti_fast_fail_never_calls_ai_provider():
    loan = fake_loan("70000", "100000")
    with patch("loanpulse_app.services._gemini_assessment") as gemini, patch("loanpulse_app.services._groq_assessment") as groq:
        result, provider = assess_loan(loan)
    assert provider == "rules"
    assert result["decision_status"] == "REJECTED"
    assert result["risk_score"] == 95
    gemini.assert_not_called()
    groq.assert_not_called()


def test_gemini_assessment_wins_provider_cascade():
    loan = fake_loan()
    assessment = {"risk_score": 25, "reasoning": "Low risk.", "decision_status": "APPROVED"}
    with patch("loanpulse_app.services._gemini_assessment", return_value=assessment), patch("loanpulse_app.services._groq_assessment") as groq:
        actual, provider = assess_loan(loan)
    assert provider == "gemini"
    assert actual["risk_score"] == assessment["risk_score"]
    assert actual["decision_status"] == "UNDER_REVIEW"
    groq.assert_not_called()


def test_groq_is_used_if_gemini_fails_and_bad_ai_falls_back_to_rules():
    loan = fake_loan()
    assessment = {"risk_score": 65, "reasoning": "Review financial records.", "decision_status": "UNDER_REVIEW"}
    with patch("loanpulse_app.services._gemini_assessment", side_effect=TimeoutError), patch("loanpulse_app.services._groq_assessment", return_value=assessment):
        actual, provider = assess_loan(loan)
    assert provider == "groq"
    assert actual == assessment

    with patch("loanpulse_app.services._gemini_assessment", side_effect=ValueError("bad response")), patch("loanpulse_app.services._groq_assessment", side_effect=TimeoutError):
        actual, provider = assess_loan(loan)
    assert provider == "rules"
    assert actual["decision_status"] == "UNDER_REVIEW"
    assert "provider unavailable" in actual["reasoning"]


def test_lti_thresholds_are_configurable():
    loan = fake_loan("30000", "100000")
    with override_settings(LTI_REVIEW_THRESHOLD=0.25, LTI_REJECTION_THRESHOLD=0.50, GEMINI_API_KEY="", GROQ_API_KEY=""):
        result, provider = assess_loan(loan)
    assert provider == "rules"
    assert result["decision_status"] == "UNDER_REVIEW"


def test_model_cannot_approve_mandatory_review_band():
    loan = fake_loan("50000", "100000")
    approved = {"risk_score": 20, "reasoning": "Looks fine.", "decision_status": "APPROVED"}
    with patch("loanpulse_app.services._gemini_assessment", return_value=approved), patch("loanpulse_app.services._groq_assessment", return_value=approved):
        result, provider = assess_loan(loan)
    assert provider == "rules"
    assert result["decision_status"] == "UNDER_REVIEW"


def test_ai_response_validation():
    assert _extract_assessment('```json\n{"risk_score": 12, "reasoning": "Low risk", "decision_status": "APPROVED"}\n```')["risk_score"] == 12
    with pytest.raises((ValueError, KeyError)):
        _extract_assessment('{"risk_score": 200, "reasoning": "x", "decision_status": "APPROVED"}')
    with pytest.raises(Exception):
        _extract_assessment("not JSON")


def test_gemini_and_groq_sdk_boundaries_parse_provider_results():
    loan = fake_loan()
    payload = '{"risk_score": 24, "reasoning": "Stable loan-to-income ratio.", "decision_status": "APPROVED"}'
    gemini_response = SimpleNamespace(text=payload)
    gemini_client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: gemini_response))
    with override_settings(GEMINI_API_KEY="test-key"), patch("google.genai.Client", return_value=gemini_client) as client:
        from loanpulse_app.services import _gemini_assessment
        assert _gemini_assessment(loan)["risk_score"] == 24
        client.assert_called_once()

    groq_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])
    groq_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: groq_response)))
    with override_settings(GROQ_API_KEY="test-key"), patch("groq.Groq", return_value=groq_client) as client:
        from loanpulse_app.services import _groq_assessment
        assert _groq_assessment(loan)["decision_status"] == "APPROVED"
        client.assert_called_once()


def test_karzai_topic_filter_static_answers_and_bounded_gemini():
    cache.clear()
    assert not karzai_is_loan_query("Tell me a joke about a loan")
    assert not karzai_is_loan_query("What is a loan rate and write code to hack a server")
    assert karzai_is_loan_query("What is the current interest rate for a home loan?")
    assert karzai_is_loan_query("What's the current interest rate for xyz category?")
    with override_settings(GEMINI_API_KEY="test-key"):
        with patch("google.genai.Client") as client:
            answer = karzai_reply("What is the current interest rate for a home loan?")
            assert "does not currently publish" in answer
            assert "does not currently publish" in karzai_reply("What's the current interest rate for xyz category?")
            client.assert_not_called()

        response = SimpleNamespace(text="A loan term is the scheduled repayment duration.")
        generate_content = Mock(return_value=response)
        model_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with patch("google.genai.Client", return_value=model_client) as client:
            answer = karzai_reply("What does a loan term mean?")
            assert "loan term" in answer
            generate_content.assert_called_once()
            call = generate_content.call_args.kwargs
            assert call["config"]["max_output_tokens"] == 120
            assert call["config"]["temperature"] == 0


def test_kyc_ai_review_has_small_output_and_does_not_return_document_pii(tmp_path):
    cache.clear()
    document_path = tmp_path / "proof.pdf"
    document_path.write_bytes(b"%PDF-1.4 fake private data")
    document = SimpleNamespace(
        content_type="application/pdf", file_path=str(document_path), document_type="ID_PROOF",
    )
    response = SimpleNamespace(text=(
        '{"readability":"clear","visible_expiry":"valid",'
        '"missing_items":["Text is difficult to read","PERSONAL ID 123456"],'
        '"document_type":"ID 123456","next_step":"Call PERSON with ID 123456"}'
    ))
    generate_content = Mock(return_value=response)
    model_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    with override_settings(MEDIA_ROOT=tmp_path, GEMINI_API_KEY="test-key"), patch("google.genai.Client", return_value=model_client):
        result = review_kyc_document(document)
        assert review_kyc_document(document) == result
    assert result["document_type"] == "ID_PROOF"
    assert result["missing_items"] == ["Text is difficult to read"]
    assert "123456" not in str(result)
    assert "does not verify identity" in result["disclaimer"]
    assert generate_content.call_count == 1
    assert generate_content.call_args.kwargs["config"]["max_output_tokens"] == 180


@pytest.mark.django_db
@override_settings(GEMINI_API_KEY="", GROQ_API_KEY="")
def test_borrower_chat_filter_and_submission_feedback_are_scoped():
    borrower = User.objects.create(
        email="karzai-borrower@example.com", full_name="KARZai Borrower", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(borrower)}")
    with patch("loanpulse_app.views.karzai_reply") as reply:
        off_topic = client.post("/karzai/chat", {"question": "Tell me a joke"}, format="json")
        assert off_topic.status_code == 200
        assert "loan" in off_topic.data["answer"].lower()
        reply.assert_not_called()
    static = client.post("/karzai/chat", {"question": "What is the interest rate for a home loan?"}, format="json")
    assert "does not currently publish" in static.data["answer"]
    assert client.post("/karzai/chat", {"question": "x" * 281}, format="json").status_code == 400

    created = client.post("/applications/", {
        "applicant_name": "Forged Name", "applicant_email": "someone@example.com",
        "annual_income": "50000", "requested_amount": "10000", "loan_purpose": "PERSONAL",
    }, format="json")
    assert created.status_code == 201
    assert created.data["borrower_feedback"]
    assert "risk_reasoning" not in created.data
    assert "applicant_email" not in created.data


@pytest.mark.django_db
def test_kyc_review_requires_consent_and_enforces_document_ownership(tmp_path):
    borrower = User.objects.create(
        email="kyc-owner@example.com", full_name="KYC Owner", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    other = User.objects.create(
        email="kyc-other@example.com", full_name="KYC Other", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    loan = LoanApplication.objects.create(
        applicant_user=borrower, applicant_name=borrower.full_name, annual_income=50000, requested_amount=10000,
    )
    other_loan = LoanApplication.objects.create(
        applicant_user=other, applicant_name=other.full_name, annual_income=50000, requested_amount=10000,
    )
    own_path = tmp_path / "proof.pdf"
    own_path.write_bytes(b"%PDF-1.4 test")
    own_doc = LoanDocument.objects.create(
        loan=loan, document_type="ID_PROOF", file_name="proof.pdf", file_path=str(own_path),
        file_size_bytes=own_path.stat().st_size, content_type="application/pdf",
    )
    private_doc = LoanDocument.objects.create(
        loan=other_loan, document_type="ID_PROOF", file_name="private.pdf", file_path=str(own_path),
        file_size_bytes=own_path.stat().st_size, content_type="application/pdf",
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(borrower)}")
    with override_settings(MEDIA_ROOT=tmp_path), patch("loanpulse_app.views.KycReviewThrottle.allow_request", return_value=True), patch("loanpulse_app.views.review_kyc_document", return_value={"readability": "clear"}) as review:
        assert client.post(f"/karzai/documents/{own_doc.id}/review", {"consent": False}, format="json").status_code == 400
        assert client.post(f"/karzai/documents/{private_doc.id}/review", {"consent": True}, format="json").status_code == 404
        response = client.post(f"/karzai/documents/{own_doc.id}/review", {"consent": True}, format="json")
        assert response.status_code == 200
        review.assert_called_once_with(own_doc)


def test_emi_schedule_uses_decimal_rounding_and_reconciles():
    assert calculate_emi("1200", "0", 12) == Decimal("100.00")
    schedule = generate_schedule("1000", "12", 12, date(2025, 1, 31))
    assert len(schedule) == 12
    assert schedule[0]["due_date"] == date(2025, 2, 28)
    assert sum(row["principal_component"] for row in schedule) == Decimal("1000.00")


@pytest.mark.django_db
@override_settings(GEMINI_API_KEY="", GROQ_API_KEY="")
def test_authenticated_lending_workflow_and_partial_payment():
    user = User.objects.create(email="officer@example.com", full_name="Loan Officer", role="ADMIN", hashed_password=make_password("LongEnoughPassword!123"))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(user)}")

    created = client.post("/applications/", {
        "applicant_name": "Jordan Example", "applicant_email": "jordan@example.com",
        "annual_income": "60000", "requested_amount": "12000",
        "requested_term_months": 12, "employment_type": "SALARIED", "loan_purpose": "PERSONAL",
    }, format="json")
    assert created.status_code == 201, created.data
    loan_id = created.data["id"]
    assert created.data["status"] == "UNDER_REVIEW"
    assert created.data["risk_score"] is not None

    approved = client.patch(f"/applications/{loan_id}/status", {"status": "APPROVED"}, format="json")
    assert approved.status_code == 200

    disbursement = client.post("/disbursements/", {
        "loan_id": loan_id, "disbursed_amount": "12000", "interest_rate": "12.5",
        "disbursement_date": "2026-01-15", "payment_method": "BANK_TRANSFER",
    }, format="json")
    assert disbursement.status_code == 201, disbursement.data
    assert RepaymentSchedule.objects.filter(loan_id=loan_id).count() == 12
    duplicate = client.post("/disbursements/", {
        "loan_id": loan_id, "disbursed_amount": "12000", "interest_rate": "12.5",
        "disbursement_date": "2026-01-15", "payment_method": "BANK_TRANSFER",
    }, format="json")
    assert duplicate.status_code == 409

    first = RepaymentSchedule.objects.get(loan_id=loan_id, installment_number=1)
    partial = client.post(f"/repayments/{loan_id}/pay/{first.id}", {"paid_amount": "10"}, format="json")
    assert partial.status_code == 200
    first.refresh_from_db()
    assert first.status == "PENDING"
    assert first.paid_amount == Decimal("10.00")

    remainder = client.post(f"/repayments/{loan_id}/pay/{first.id}", {"paid_amount": str(first.emi_amount - first.paid_amount)}, format="json")
    assert remainder.status_code == 200
    first.refresh_from_db()
    assert first.status == "PAID"

    summary = client.get(f"/repayments/{loan_id}")
    assert summary.status_code == 200
    assert summary.data["paid_count"] == 1
    assert summary.data["total_installments"] == 12
    assert client.get(f"/repayments/{loan_id}/export-csv").status_code == 200
    assert client.get("/dashboard/kpis").data["total_applications"] == 1


@pytest.mark.django_db
def test_login_rejects_bad_password_and_issues_token():
    User.objects.create(email="login@example.com", full_name="Officer", role="OFFICER", hashed_password=make_password("CorrectPassword!123"))
    client = APIClient()
    assert client.post("/auth/login", {"username": "login@example.com", "password": "bad"}).status_code == 401
    response = client.post("/auth/login", {"username": "login@example.com", "password": "CorrectPassword!123"})
    assert response.status_code == 200
    assert response.data["token_type"] == "bearer"


@pytest.mark.django_db
def test_login_supports_existing_bcrypt_password_hashes():
    import bcrypt
    User.objects.create(
        email="legacy@example.com", full_name="Legacy Officer", role="ADMIN",
        hashed_password=bcrypt.hashpw(b"LegacyPassword!123", bcrypt.gensalt()).decode(),
    )
    response = APIClient().post("/auth/login", {"username": "legacy@example.com", "password": "LegacyPassword!123"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_application_endpoints_require_authentication():
    response = APIClient().get("/applications/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_health_and_frontend_are_served_by_django():
    client = APIClient()
    home = client.get("/")
    assert home.status_code == 200
    assert "name@company.com" in home.content.decode()
    assert "admin@loanpulse.local" not in home.content.decode()
    assert 'data-lti-review-threshold="40"' in home.content.decode()
    assert 'href="/static/tailwind.' in home.content.decode()
    assert 'id="signupForm"' in home.content.decode()
    assert 'id="view-borrower"' in home.content.decode()
    assert client.get("/health").status_code == 200


@pytest.mark.django_db
def test_document_upload_download_and_delete():
    user = User.objects.create(email="docs@example.com", full_name="Officer", role="ADMIN", hashed_password=make_password("LongEnoughPassword!123"))
    loan = LoanApplication.objects.create(applicant_name="Document Test", annual_income=50000, requested_amount=10000, assigned_officer=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(user)}")
    invalid = SimpleUploadedFile("statement.exe", b"bad", content_type="application/octet-stream")
    assert client.post(f"/applications/{loan.id}/documents", {"document_type": "ID_PROOF", "file": invalid}, format="multipart").status_code == 400

    pdf = SimpleUploadedFile("proof.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    uploaded = client.post(f"/applications/{loan.id}/documents", {"document_type": "ID_PROOF", "file": pdf}, format="multipart")
    assert uploaded.status_code == 201, uploaded.data
    document_id = uploaded.data["id"]
    assert client.get(f"/documents/{document_id}/download").status_code == 200
    assert client.delete(f"/documents/{document_id}").status_code == 204
    assert not loan.documents.filter(pk=document_id).exists()


@pytest.mark.django_db
def test_viewer_cannot_change_loan_data():
    viewer = User.objects.create(email="viewer@example.com", full_name="Read Only", role="VIEWER", hashed_password=make_password("LongEnoughPassword!123"))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(viewer)}")
    response = client.post("/applications/", {
        "applicant_name": "Jordan Example", "annual_income": "60000", "requested_amount": "12000",
    }, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_overdue_check_marks_due_installments_without_assessing_unconfigured_fees():
    user = User.objects.create(
        email="collections@example.com", full_name="Collections Officer", role="OFFICER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    loan = LoanApplication.objects.create(
        applicant_name="Overdue Test", annual_income=50000, requested_amount=10000,
    )
    overdue = RepaymentSchedule.objects.create(
        loan=loan, installment_number=1, due_date=date.today() - timedelta(days=1),
        emi_amount="1000.00", principal_component="900.00", interest_component="100.00",
    )
    future = RepaymentSchedule.objects.create(
        loan=loan, installment_number=2, due_date=date.today() + timedelta(days=30),
        emi_amount="1000.00", principal_component="910.00", interest_component="90.00",
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(user)}")

    response = client.post("/repayments/batch/trigger-overdue-check", {}, format="json")

    assert response.status_code == 200
    assert response.data["overdue_check"]["marked_overdue"] == 1
    overdue.refresh_from_db()
    future.refresh_from_db()
    assert overdue.status == "OVERDUE"
    assert overdue.penalty_amount == Decimal("0.00")
    assert future.status == "PENDING"
    assert overdue.loan.audit_log.filter(action="INSTALLMENT_OVERDUE").exists()


@pytest.mark.django_db
def test_public_signup_creates_borrower_only_account_and_token():
    response = APIClient().post("/auth/signup", {
        "full_name": "Taylor Borrower", "email": "Taylor@example.com",
        "password": "SecureBorrowerPass!42", "role": "ADMIN",
    }, format="json")

    assert response.status_code == 201, response.data
    user = User.objects.get(email="taylor@example.com")
    assert user.role == "CUSTOMER"
    assert response.data["user"]["role"] == "CUSTOMER"
    assert response.data["access_token"]
    assert APIClient().post("/auth/signup", {
        "full_name": "Taylor Borrower", "email": "taylor@example.com",
        "password": "SecureBorrowerPass!42",
    }, format="json").status_code == 409
    assert APIClient().post("/auth/signup", {
        "full_name": "Numeric Password", "email": "numeric@example.com",
        "password": "123456789012",
    }, format="json").status_code == 400


@pytest.mark.django_db
@override_settings(BOSS_EMAIL="boss@example.com")
def test_staff_signup_is_inactive_until_boss_approves_and_can_be_reverted():
    signup = APIClient().post("/auth/signup", {
        "full_name": "Staff Applicant", "email": "staff-applicant@example.com",
        "password": "SecureStaffPass!42", "account_type": "STAFF",
    }, format="json")
    assert signup.status_code == 201
    assert "after the boss approves" in signup.data["detail"]
    applicant = User.objects.get(email="staff-applicant@example.com")
    assert not applicant.is_active
    assert applicant.staff_registration_status == "PENDING"
    assert APIClient().post("/auth/login", {"username": applicant.email, "password": "SecureStaffPass!42"}).status_code == 401

    boss = User.objects.create(email="boss@example.com", full_name="Boss", role="ADMIN", is_active=True, hashed_password=make_password("BossPass!123456"))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(boss)}")
    assert len(client.get("/auth/staff-registrations?status=pending").data) == 1
    assert client.post("/auth/staff-registrations", {"user_id": applicant.id, "status": "approved"}, format="json").status_code == 200
    applicant.refresh_from_db()
    assert applicant.is_active and applicant.staff_registration_status == "APPROVED"
    assert client.post("/auth/staff-registrations", {"user_id": applicant.id, "status": "disapproved"}, format="json").status_code == 200
    applicant.refresh_from_db()
    assert not applicant.is_active and applicant.staff_registration_status == "DISAPPROVED"
    assert client.post("/auth/staff-registrations", {"user_id": applicant.id, "status": "pending"}, format="json").status_code == 200
    applicant.refresh_from_db()
    assert not applicant.is_active and applicant.staff_registration_status == "PENDING"


@pytest.mark.django_db
@override_settings(BOSS_EMAIL="boss@example.com")
def test_only_configured_boss_can_review_staff_registrations():
    admin = User.objects.create(email="other-admin@example.com", full_name="Other Admin", role="ADMIN", hashed_password=make_password("BossPass!123456"))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(admin)}")
    assert client.get("/auth/staff-registrations").status_code == 403
    assert client.post("/auth/register", {}, format="json").status_code == 404


@pytest.mark.django_db
@override_settings(GEMINI_API_KEY="", GROQ_API_KEY="")
def test_borrower_can_apply_and_only_see_own_applications_and_tracking():
    borrower = User.objects.create(
        email="borrower@example.com", full_name="Avery Borrower", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    other = User.objects.create(
        email="other@example.com", full_name="Morgan Other", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    own_client = APIClient()
    own_client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(borrower)}")
    other_client = APIClient()
    other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(other)}")

    created = own_client.post("/applications/", {
        "applicant_name": "Impersonated Name", "applicant_email": "somebody-else@example.com",
        "annual_income": "80000", "requested_amount": "20000",
        "requested_term_months": 36, "employment_type": "SALARIED", "loan_purpose": "VEHICLE",
    }, format="json")
    assert created.status_code == 201, created.data
    loan = LoanApplication.objects.get(pk=created.data["id"])
    assert loan.applicant_user_id == borrower.id
    assert loan.applicant_name == borrower.full_name
    assert loan.applicant_email == borrower.email
    assert loan.loan_purpose == "VEHICLE"

    other_loan = LoanApplication.objects.create(
        applicant_user=other, applicant_name=other.full_name, applicant_email=other.email,
        annual_income=90000, requested_amount=10000, loan_purpose="EDUCATION",
    )
    for linked_loan, amount in ((loan, "20000.00"), (other_loan, "10000.00")):
        Disbursement.objects.create(
            loan=linked_loan, disbursed_amount=amount, interest_rate="5.0000",
            disbursement_date=date.today(), payment_method="BANK_TRANSFER",
        )
        RepaymentSchedule.objects.create(
            loan=linked_loan, installment_number=1, due_date=date.today() - timedelta(days=1),
            emi_amount="1000.00", principal_component="900.00", interest_component="100.00",
            status="OVERDUE",
        )
    assert [row["id"] for row in own_client.get("/applications/").data] == [loan.id]
    assert own_client.get("/applications/?search=Morgan").data == []
    assert sum(own_client.get("/applications/count").data.values()) == 1
    dashboard = own_client.get("/dashboard/kpis").data
    assert dashboard["total_applications"] == 1
    assert dashboard["total_disbursed_amount"] == 20000
    assert dashboard["total_overdue_installments"] == 1
    details = own_client.get(f"/applications/{loan.id}/details")
    assert details.status_code == 200
    assert details.data["loan_purpose"] == "VEHICLE"
    assert "risk_reasoning" not in details.data
    assert "applicant_email" not in details.data
    assert len(details.data["schedule"]) == 1
    assert own_client.get(f"/applications/{other_loan.id}/details").status_code == 404
    assert own_client.get(f"/applications/{other_loan.id}/audit").status_code == 404
    assert own_client.get(f"/repayments/{loan.id}").status_code == 200
    assert own_client.get(f"/repayments/{other_loan.id}").status_code == 404
    assert len(own_client.get("/repayments/overdue/all").data) == 1
    assert own_client.get(f"/disbursements/{other_loan.id}").status_code == 404
    assert len(own_client.get("/disbursements/").data) == 1
    assert own_client.patch(f"/applications/{loan.id}/status", {"status": "APPROVED"}, format="json").status_code == 403
    other_notice = Notification.objects.create(
        recipient_email=other.email, loan=other_loan, type="IN_APP", event="STATUS",
        subject="Private update", body="Private borrower update", status="SENT",
    )
    Notification.objects.create(
        recipient_email=borrower.email, loan=None, type="IN_APP", event="UNLINKED",
        subject="Unlinked update", body="Not proven to belong to this account", status="SENT",
    )
    own_notices = own_client.get("/notifications/").data
    assert len(own_notices) == 1
    assert own_notices[0]["loan_id"] == loan.id
    assert own_client.patch(f"/notifications/{other_notice.id}/read", {}, format="json").status_code == 404
    assert other_client.get("/notifications/").data[0]["loan_id"] == other_loan.id
    assert own_client.post("/auth/register", {
        "email": "attacker@example.com", "full_name": "Attacker",
        "password": "AnotherSecurePass!123", "role": "ADMIN",
    }, format="json").status_code == 404
    assert own_client.get(f"/repayments/{loan.id}/export-csv").status_code == 200
    own_schedule = loan.repayment_schedule.get()
    assert own_client.post(
        f"/repayments/{loan.id}/pay/{own_schedule.id}", {"paid_amount": "1.00"}, format="json",
    ).status_code == 403


@pytest.mark.django_db
def test_borrower_can_upload_own_documents_but_cannot_read_other_files(tmp_path):
    borrower = User.objects.create(
        email="borrower-docs@example.com", full_name="Document Borrower", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    other = User.objects.create(
        email="other-docs@example.com", full_name="Other Borrower", role="CUSTOMER",
        hashed_password=make_password("LongEnoughPassword!123"),
    )
    own_loan = LoanApplication.objects.create(
        applicant_user=borrower, applicant_name=borrower.full_name, annual_income=50000, requested_amount=10000,
    )
    other_loan = LoanApplication.objects.create(
        applicant_user=other, applicant_name=other.full_name, annual_income=50000, requested_amount=10000,
    )
    own_client = APIClient()
    own_client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(borrower)}")
    with override_settings(MEDIA_ROOT=tmp_path):
        pdf = SimpleUploadedFile("income.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        uploaded = own_client.post(
            f"/applications/{own_loan.id}/documents",
            {"document_type": "INCOME_PROOF", "file": pdf}, format="multipart",
        )
        assert uploaded.status_code == 201, uploaded.data
        document_id = uploaded.data["id"]
        assert own_client.get(f"/documents/{document_id}/download").status_code == 200

        other_doc = LoanDocument.objects.create(
            loan=other_loan, document_type="ID_PROOF", file_name="private.pdf",
            file_path=str(tmp_path / "private.pdf"), file_size_bytes=1, content_type="application/pdf",
        )
        assert own_client.get(f"/documents/{other_doc.id}/download").status_code == 404
        assert own_client.get(f"/applications/{other_loan.id}/documents").status_code == 404
