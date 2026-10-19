"""
app/services/__init__.py

Backward-compatibility shim.
Old code that imports from app.services still works.
"""
from app.services.risk_engine import evaluate_loan_risk

__all__ = ["evaluate_loan_risk"]
