"""
tests/test_risk_engine.py — Unit tests for deterministic rules and DTI calculations.
"""
from app.services.risk_engine import calculate_dti, deterministic_assessment


class DummyLoan:
    def __init__(self, applicant_name, annual_income, requested_amount):
        self.applicant_name = applicant_name
        self.annual_income = annual_income
        self.requested_amount = requested_amount


def test_calculate_dti():
    dti = calculate_dti(30000, 100000)
    assert dti == 0.30


def test_deterministic_assessment_auto_reject():
    # DTI > 60% should auto-reject with high risk score
    loan = DummyLoan("High Debt User", 50000, 40000) # 80% DTI
    res = deterministic_assessment(loan)
    assert res["decision_status"] == "REJECTED"
    assert res["risk_score"] >= 90
    assert "exceeds" in res["reasoning"].lower()


def test_deterministic_assessment_under_review():
    # DTI between 40% and 60%
    loan = DummyLoan("Borderline User", 100000, 50000) # 50% DTI
    res = deterministic_assessment(loan)
    assert res["decision_status"] == "UNDER_REVIEW"
    assert 50 <= res["risk_score"] <= 90


def test_deterministic_assessment_approved():
    # DTI < 40%
    loan = DummyLoan("Prime Borrower", 120000, 24000) # 20% DTI
    res = deterministic_assessment(loan)
    assert res["decision_status"] == "APPROVED"
    assert res["risk_score"] < 50
