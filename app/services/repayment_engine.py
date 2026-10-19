"""
app/services/repayment_engine.py — Standard EMI and Amortization Calculation.
Uses standard reducing-balance monthly amortization formula.
"""
from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any


def calculate_emi(principal: float, annual_rate: float, term_months: int) -> float:
    """
    Calculate fixed monthly EMI using reducing balance formula:
    EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
    where:
      P = principal
      r = monthly interest rate (annual_rate / 12 / 100)
      n = number of months
    """
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    if principal <= 0:
        raise ValueError("principal must be positive")

    r = (annual_rate / 12.0) / 100.0
    if r == 0:
        return round(principal / term_months, 2)

    factor = (1.0 + r) ** term_months
    emi = principal * r * factor / (factor - 1.0)
    return round(emi, 2)


def generate_amortization_schedule(
    principal: float,
    annual_rate: float,
    term_months: int,
    disbursement_date: date,
) -> List[Dict[str, Any]]:
    """
    Generates a full installment-by-installment schedule.
    Each month calculates interest on remaining balance, deducts principal,
    and advances due_date by 1 month.
    """
    emi = calculate_emi(principal, annual_rate, term_months)
    monthly_rate = (annual_rate / 12.0) / 100.0
    balance = principal
    schedule = []

    for month in range(1, term_months + 1):
        due_date = disbursement_date + relativedelta(months=month)
        interest_comp = round(balance * monthly_rate, 2)

        # On the final installment, reconcile any cents difference
        if month == term_months:
            principal_comp = round(balance, 2)
            actual_emi = round(principal_comp + interest_comp, 2)
            balance = 0.0
        else:
            principal_comp = round(emi - interest_comp, 2)
            balance = round(balance - principal_comp, 2)
            actual_emi = emi

        schedule.append({
            "installment_number": month,
            "due_date": due_date,
            "emi_amount": actual_emi,
            "principal_component": principal_comp,
            "interest_component": interest_comp,
            "status": "PENDING",
        })

    return schedule
