"""
tests/test_repayment_engine.py — Unit tests for EMI and Amortization schedule.
"""
from datetime import date
from app.services.repayment_engine import calculate_emi, generate_amortization_schedule


def test_calculate_emi_zero_interest():
    """At 0% interest, EMI should be principal / term."""
    emi = calculate_emi(12000, 0, 12)
    assert emi == 1000.0


def test_calculate_emi_standard():
    """Test standard reducing balance calculation: $100k @ 12% for 12 months = ~$8,884.88"""
    emi = calculate_emi(100000, 12, 12)
    assert 8880 < emi < 8890


def test_amortization_schedule_reconciliation():
    """Verify that sum of principal components matches the original principal exactly."""
    principal = 50000.0
    rate = 14.5
    term = 24
    start_date = date(2026, 1, 1)

    schedule = generate_amortization_schedule(principal, rate, term, start_date)
    assert len(schedule) == 24

    total_principal_paid = sum(item["principal_component"] for item in schedule)
    assert round(total_principal_paid, 2) == principal

    # Verify dates increment sequentially
    for i in range(len(schedule) - 1):
        assert schedule[i]["due_date"] < schedule[i + 1]["due_date"]
