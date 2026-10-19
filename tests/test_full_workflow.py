"""
tests/test_full_workflow.py — End-to-end integration test across all lending domains.
"""
import pytest
from datetime import date


@pytest.mark.asyncio
async def test_full_lending_lifecycle(async_client, auth_headers):
    # 1. Register a new loan officer
    officer_email = f"officer_workflow@loanpulse.local"
    reg_res = await async_client.post("/auth/register", json={
        "email": officer_email,
        "password": "SecurePassword123!",
        "full_name": "Integration Tester",
        "role": "OFFICER",
    })
    # Might already exist from prior run, so 201 or 400 is fine
    assert reg_res.status_code in [201, 400]

    # 2. Login
    login_res = await async_client.post("/auth/login", data={
        "username": officer_email,
        "password": "SecurePassword123!",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create Loan Application (Prime borrower: $120k income, $24k loan, 12 months)
    create_res = await async_client.post("/applications/", headers=headers, json={
        "applicant_name": "Diana Prince",
        "applicant_email": "diana@example.com",
        "annual_income": 120000.0,
        "requested_amount": 24000.0,
        "requested_term_months": 12,
        "loan_purpose": "BUSINESS",
        "employment_type": "SALARIED",
    })
    assert create_res.status_code == 201
    loan_id = create_res.json()["id"]
    assert create_res.json()["status"] == "PENDING"

    # 4. Manually advance status to APPROVED for disbursement
    status_res = await async_client.patch(
        f"/applications/{loan_id}/status",
        headers=headers,
        json={"status": "APPROVED"}
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "APPROVED"

    # 5. Disburse Loan
    disb_res = await async_client.post("/disbursements/", headers=headers, json={
        "loan_id": loan_id,
        "disbursed_amount": 24000.0,
        "interest_rate": 10.5,
        "disbursement_date": date.today().isoformat(),
        "payment_method": "BANK_TRANSFER",
        "bank_reference": "WIRE-99281",
    })
    assert disb_res.status_code == 201
    assert disb_res.json()["loan_id"] == loan_id

    # 6. Retrieve generated repayment schedule
    rep_res = await async_client.get(f"/repayments/{loan_id}", headers=headers)
    assert rep_res.status_code == 200
    summary = rep_res.json()
    assert summary["total_installments"] == 12
    assert summary["pending_count"] == 12
    assert summary["paid_count"] == 0
    assert summary["total_paid"] == 0.0
    assert summary["total_emi"] > 24000.0  # principal + interest

    # 7. Record payment for Installment #1
    first_inst = summary["schedule"][0]
    pay_res = await async_client.post(
        f"/repayments/{loan_id}/pay/{first_inst['id']}",
        headers=headers,
        json={"paid_amount": first_inst["emi_amount"]}
    )
    assert pay_res.status_code == 200
    assert pay_res.json()["status"] == "PAID"

    # 8. Verify updated repayment summary
    rep_after = await async_client.get(f"/repayments/{loan_id}", headers=headers)
    assert rep_after.status_code == 200
    after_data = rep_after.json()
    assert after_data["paid_count"] == 1
    assert after_data["pending_count"] == 11
    assert after_data["total_paid"] == first_inst["emi_amount"]

    # 9. Verify KPI dashboard reflects the new disbursed capital
    kpi_res = await async_client.get("/dashboard/kpis", headers=headers)
    assert kpi_res.status_code == 200
    kpis = kpi_res.json()
    assert kpis["total_disbursed_amount"] >= 24000.0

    # 10. Verify audit trail exists for this loan
    audit_res = await async_client.get(f"/applications/{loan_id}/audit", headers=headers)
    assert audit_res.status_code == 200
    actions = [a["action"] for a in audit_res.json()]
    assert "APPLICATION_SUBMITTED" in actions
    assert "LOAN_DISBURSED" in actions
    assert "PAYMENT_RECORDED" in actions
