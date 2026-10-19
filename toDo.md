# LoanPulse — To Do

Last updated: 2026-10-19

> All Core Phases (1 through 9) are **100% COMPLETED AND VERIFIED**!
> The full lending lifecycle (application, AI underwriting, KYC document attachments, deep audit timeline, disbursement, repayment, CSV export, notifications, auth, Apple glass UI, automated tests) is working end-to-end.

---

## Completed Phases Overview
- [x] **Phase 1**: Backend Foundation (FastAPI, PostgreSQL, Alembic, Docker)
- [x] **Phase 2**: AI Underwriting & DTI Fast-Fail Heuristics (Gemini/Groq free cascade)
- [x] **Phase 3**: Full Database Schema Expansion & JWT Authentication (RBAC)
- [x] **Phase 4**: Loan Disbursement & EMI Amortization Repayment Engine (Exact reducing balance)
- [x] **Phase 5**: Email & In-App Notification System with Periodic Arrears Scheduler
- [x] **Phase 6**: Full-Stack Single Page Application Frontend (Dashboard, Pipeline, Servicing, Notifications)
- [x] **Phase 7**: Automated Pytest Test Suite (8/8 tests passing)
- [x] **Phase 8**: Apple Liquid Glass UI Design, Responsive Mobile Dock, and Google Sans Typography
- [x] **Phase 9**: KYC Document Attachments (Local storage, zero cost), Deep Audit Timeline Modal, and Amortization CSV Export (9/9 tests passing)

---

## Optional Future Architectural Scale Items (Post-Production)
- [ ] Celery + Redis worker if scaling background AI underwriting beyond in-process `BackgroundTasks`
- [ ] WebSocket live push notifications instead of interval polling
- [ ] Direct OCR parsing on uploaded KYC documents using local Tesseract (free/open-source)

---

## How to Run & Verify

```bash
cd /home/adirchy/Projects/loanpulse

# 1. Run full test suite
venv/bin/pytest tests/ -v

# 2. Start Uvicorn development server
venv/bin/uvicorn app.main:app --reload --port 8000

# 3. Open Web UI in browser (Mobile & Laptop ready)
# URL: http://localhost:8000
# Default Login:
#   Email: admin@loanpulse.local
#   Password: Admin123!

# 4. View interactive learning dashboards in your browser
# File: file:///home/adirchy/Projects/loanpulse/glass_learning_dashboard.html
# File: file:///home/adirchy/Projects/loanpulse/phase1_learning_dashboard.html
# File: file:///home/adirchy/Projects/loanpulse/phase2_learning_dashboard.html
```
