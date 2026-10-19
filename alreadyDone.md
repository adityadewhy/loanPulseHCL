# LoanPulse — Already Done

Last updated: 2026-10-15

---

## Phase 1 — Backend Foundation ✅
- [x] FastAPI app created (`app/main.py`)
- [x] PostgreSQL 15 via Docker Compose (`docker-compose.yml`)
- [x] Async SQLAlchemy engine + session factory (`app/database.py`)
- [x] Alembic initialized with async `env.py` (`alembic/`)
- [x] `LoanApplication` ORM model created
- [x] Pydantic v2 schemas: `LoanApplicationCreate`, `LoanApplicationResponse`, `LoanStatusUpdate`
- [x] Pydantic Settings via `.env` (`app/config.py`)
- [x] **Migration `c47c7f042184`**: creates `loan_applications` table
- [x] Basic CRUD endpoints: POST, GET, PATCH status

## Phase 2 — AI Risk Assessment ✅
- [x] `risk_score` and `risk_reasoning` columns added to `LoanApplication`
- [x] **Migration `cded32d10d3f`**: adds risk columns (nullable)
- [x] `app/services/risk_engine.py`: Multi-provider cascade (Gemini → Groq → Deterministic DTI)
- [x] FastAPI `BackgroundTasks` dispatches evaluation after loan creation (returns 201 immediately)
- [x] DTI fast-fail rule: DTI > 60% → instant REJECTED, risk_score=95, no AI call
- [x] Graceful degradation: AI failures never crash the API, safe fallback to UNDER_REVIEW
- [x] Gemini API key configured in `.env`

## Phase 3 — Full Schema Expansion & Authentication ✅
- [x] Installed packages: `python-jose[cryptography]`, `bcrypt`, `aiosmtplib`, `python-multipart`, `python-dateutil`, `google-generativeai`, `groq`, `httpx`, `pytest`, `pytest-asyncio`
- [x] Fully expanded `app/models.py` with all 6 tables:
  - `User`: email, hashed_password, full_name, role, is_active, created_at
  - `LoanApplication`: applicant_email, applicant_phone, employment_type, loan_purpose, requested_term_months, assigned_officer_id, created_at, updated_at
  - `Disbursement`: loan_id, disbursed_amount, interest_rate, disbursement_date, payment_method, bank_reference
  - `RepaymentSchedule`: loan_id, installment_number, due_date, emi_amount, principal_component, interest_component, status, paid_date, paid_amount, penalty_amount
  - `AuditLog`: loan_id, actor_id, action, old_value, new_value, notes, timestamp
  - `Notification`: recipient_email, loan_id, type, event, subject, body, sent_at, read_at, status
- [x] **Migration `9ce96b5f5487`**: `phase3 full schema expansion` applied cleanly to PostgreSQL
- [x] Direct `bcrypt` password hashing without passlib version bugs
- [x] JWT access token creation and verification (`app/auth/utils.py`)
- [x] Auth endpoints (`app/auth/router.py`):
  - `POST /auth/register`
  - `POST /auth/login` (OAuth2 compatible form data)
  - `GET /auth/me`
- [x] Default admin user seeded on startup: `admin@loanpulse.local` / `Admin123!`

## Phase 4 — Disbursement & Repayment Engine ✅
- [x] `app/services/repayment_engine.py`:
  - `calculate_emi(principal, annual_rate, term_months)`: exact reducing balance formula
  - `generate_amortization_schedule(...)`: installment dates, principal/interest breakdown, cent reconciliation
- [x] `app/routers/disbursements.py`:
  - `POST /disbursements/`: validates APPROVED status, prevents duplicates, generates amortization schedule, sets DISBURSED status, emits audit log & customer notification
  - `GET /disbursements/{loan_id}`
  - `GET /disbursements/`
- [x] `app/routers/repayments.py`:
  - `GET /repayments/{loan_id}`: full schedule with calculated metrics (total EMI, total paid, balance, overdue count)
  - `POST /repayments/{loan_id}/pay/{installment_id}`: records payment, transitions loan to ACTIVE or CLOSED
  - `GET /repayments/overdue/all`: lists all arrears
  - `POST /repayments/batch/trigger-overdue-check`: manual batch trigger

## Phase 5 — Notification System & Overdue Scheduler ✅
- [x] `app/services/notification_service.py`:
  - Free email via `aiosmtplib` (Gmail SMTP) with safe fallback logger
  - In-app notification persistence in `notifications` table
- [x] `app/services/scheduler.py`:
  - `run_overdue_check()`: scans past-due installments, sets OVERDUE, applies 2% late fee penalty, sends alerts
  - `run_upcoming_reminders()`: notifies 3 days before due date
- [x] `app/routers/notifications.py`:
  - `GET /notifications/`
  - `GET /notifications/unread-count`
  - `PATCH /notifications/{id}/read`

## Phase 6 — Full-Stack Single Page Application Frontend ✅
- [x] Mounted `app/static/` via FastAPI `StaticFiles`
- [x] Modern, responsive dark-mode SPA (`app/static/index.html` + `app/static/app.js`):
  - Dashboard with live KPI counters (Total applications, Capital disbursed, Overdue count, Collection rate)
  - Applications list with search, status filtering, and action buttons (Approve, Reject, Disburse)
  - New Loan Application Form with live dynamic DTI calculation preview
  - Disbursements modal and schedule generation
  - Repayment tracker: installment grid, record payment button, overdue highlights
  - Notifications feed with unread badge and mark-as-read
  - Auth modal with default test credentials hint and JWT session persistence

## Phase 7 — Automated Testing & Verification ✅
- [x] `pytest.ini` with `pythonpath = .` and `asyncio_mode = auto`
- [x] `tests/conftest.py` with `async_client` and `auth_headers`
- [x] `tests/test_repayment_engine.py` (zero interest, standard EMI, schedule reconciliation)
- [x] `tests/test_risk_engine.py` (DTI calculation, auto-reject, under review, approved)
- [x] `tests/test_full_workflow.py` (complete end-to-end lending lifecycle test)
- [x] **All 8 tests passing with code 0!**

## Phase 8 — Apple Liquid Glass Theme & Responsive Mobile/Desktop UI ✅
- [x] **Apple VisionOS / iOS 18 Liquid Glass Design System (`app/static/index.html` & `app/static/app.js`)**:
  - Multi-layer frosted glass panels: `backdrop-filter: blur(28px) saturate(190%)`
  - Specular bevel edge highlights: `border: 1px solid rgba(255, 255, 255, 0.12)` + `box-shadow: inset 0 1px 1px 0 rgba(255, 255, 255, 0.25)`
  - Ambient deep space glow mesh with cyan, purple, and emerald luminous light orbs
  - Translucent jewel status pills with matching ambient glowing rings
  - Glass buttons with gradient sheen, tactile elevation on hover, and active press physics
- [x] **Phone & Laptop Ergonomics & Responsiveness**:
  - **Laptop / Desktop (>1024px)**: Left floating glass sidebar (`w-72`), floating top glass header, 4-column KPI metric cards, widescreen data tables
  - **Mobile Phone (<1024px)**: Floating bottom glass dock (`fixed bottom-3 left-3 right-3`) with quick-switch tab icons and unread alert indicator, touch-optimized inputs (min 44px tap targets), single-column stacked forms, horizontally scrollable data tables with safe dock padding (`pb-28`)
- [x] **Frontend State & Navigation Sync**:
  - `switchTab(tabId)` synchronizes active glass highlight classes across both desktop sidebar and mobile dock
  - Dynamic mobile unread notification counter dot (`#mobUnreadDot`) linked to background unread check
- [x] **Interactive Learning & Documentation Dashboard (`glass_learning_dashboard.html`)**:
  - Interactive sliders to explore glass blur radius, saturation boost, and specular lighting in real time
  - Comparative analysis of mobile vs desktop ergonomics in enterprise lending applications
- [x] **Typography Migration to Google Sans**:
  - Configured official `Google Sans` & `Google Sans Text` across `app/static/index.html` and Tailwind sans stack
  - Updated all educational dashboards (`glass_learning_dashboard.html`, `phase1_learning_dashboard.html`, `phase2_learning_dashboard.html`) with Google Sans typography

## Phase 9 — KYC Document Upload, Detailed Audit Timeline & CSV Export ✅
- [x] **Zero-Cost Local KYC Document Storage (`app/routers/documents.py`)**:
  - `loan_documents` table added via Alembic migration `1d0551d59ef0`
  - Upload KYC ID proof, salary slip, bank statements, or collateral files (`.pdf`, `.png`, `.jpg`, `.webp`) up to 15MB
  - Endpoints:
    - `POST /applications/{loan_id}/documents` (multipart file upload with automatic file sanitization and disk storage)
    - `GET /applications/{loan_id}/documents` (list attached documents)
    - `GET /documents/{document_id}/download` (stream file to browser)
    - `DELETE /documents/{document_id}` (delete physical file and database entry)
- [x] **Deep Loan Application Detail & Audit Modal (`#loanDetailModal`)**:
  - `GET /applications/{application_id}/details` eager-loads documents, audit logs, and disbursements
  - Interactive glass modal displaying applicant profile, AI Risk score & reasoning memo, attached documents with view/download links, and inline upload
  - Chronological vertical timeline of all audit events with actor attribution and notes
  - Instant action buttons (Approve, Reject, Disburse) inside modal
  - Clickable application table rows with interactive hover state
- [x] **Amortization Schedule CSV Export & Print**:
  - `GET /repayments/{loan_id}/export-csv` generates and streams formatted CSV amortization schedules
  - 1-click browser download button with JWT authentication support
  - 1-click printable statement button (`window.print()`)
- [x] **Automated Pytest Suite Expansion (`tests/test_documents_and_exports.py`)**:
  - Complete integration test covering document upload, listing, downloading, deep details inspection, CSV header/row verification, and deletion
  - Added `cleanup_db_pool` fixture in `tests/conftest.py` ensuring connection pool disposal across asyncpg test loops
  - **All 9 tests passing with 100% success!**


