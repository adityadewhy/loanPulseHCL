"""
tests/test_documents_and_exports.py — Tests for KYC document uploads, deep details, and CSV export.
"""
import pytest
import io
from datetime import date


@pytest.mark.asyncio
async def test_kyc_documents_and_export_lifecycle(async_client, auth_headers):
    # 1. Create a loan application
    app_res = await async_client.post("/applications/", headers=auth_headers, json={
        "applicant_name": "Bruce Wayne",
        "applicant_email": "bruce@wayne-enterprises.com",
        "annual_income": 350000.0,
        "requested_amount": 50000.0,
        "requested_term_months": 24,
        "loan_purpose": "BUSINESS",
        "employment_type": "SELF_EMPLOYED",
    })
    assert app_res.status_code == 201
    loan_id = app_res.json()["id"]

    # 2. Upload KYC ID proof
    fake_pdf = io.BytesIO(b"%PDF-1.4 Fake PDF Content for ID Verification")
    upload_res = await async_client.post(
        f"/applications/{loan_id}/documents",
        headers=auth_headers,
        data={"document_type": "ID_PROOF"},
        files={"file": ("passport_scan.pdf", fake_pdf, "application/pdf")},
    )
    assert upload_res.status_code == 201
    doc_data = upload_res.json()
    assert doc_data["file_name"] == "passport_scan.pdf"
    assert doc_data["document_type"] == "ID_PROOF"
    doc_id = doc_data["id"]

    # 3. List documents for loan
    list_docs_res = await async_client.get(f"/applications/{loan_id}/documents", headers=auth_headers)
    assert list_docs_res.status_code == 200
    docs = list_docs_res.json()
    assert len(docs) >= 1
    assert any(d["id"] == doc_id for d in docs)

    # 4. Download document
    dl_res = await async_client.get(f"/documents/{doc_id}/download", headers=auth_headers)
    assert dl_res.status_code == 200
    assert dl_res.content == b"%PDF-1.4 Fake PDF Content for ID Verification"

    # 5. Advance status and disburse to get repayment schedule
    await async_client.patch(
        f"/applications/{loan_id}/status",
        headers=auth_headers,
        json={"status": "APPROVED"}
    )
    disb_res = await async_client.post("/disbursements/", headers=auth_headers, json={
        "loan_id": loan_id,
        "disbursed_amount": 50000.0,
        "interest_rate": 8.0,
        "disbursement_date": date.today().isoformat(),
        "payment_method": "BANK_TRANSFER",
        "bank_reference": "TXN-BW-1002",
    })
    assert disb_res.status_code == 201

    # 6. Test Deep Application Details
    details_res = await async_client.get(f"/applications/{loan_id}/details", headers=auth_headers)
    assert details_res.status_code == 200
    details = details_res.json()
    assert details["id"] == loan_id
    assert len(details["documents"]) >= 1
    assert details["documents"][0]["file_name"] == "passport_scan.pdf"
    assert len(details["audit_log"]) >= 2
    assert details["disbursement"] is not None
    assert details["disbursement"]["disbursed_amount"] == 50000.0

    # 7. Test Amortization CSV Export
    csv_res = await async_client.get(f"/repayments/{loan_id}/export-csv", headers=auth_headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    csv_text = csv_res.text
    assert "Installment Number,Due Date,Monthly EMI ($)" in csv_text
    assert "TXN-BW-1002" not in csv_text  # CSV has schedule columns
    # Check that 24 installments are present
    assert "#1" not in csv_text  # clean integer installment numbers
    lines = csv_text.strip().split("\n")
    assert len(lines) == 25  # 1 header + 24 monthly rows

    # 8. Delete document
    del_res = await async_client.delete(f"/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # Verify document no longer in list
    docs_after = await async_client.get(f"/applications/{loan_id}/documents", headers=auth_headers)
    assert not any(d["id"] == doc_id for d in docs_after.json())
