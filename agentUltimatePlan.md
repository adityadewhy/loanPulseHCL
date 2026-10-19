# LoanPulse — Agent Ultimate Plan
# LoanMaster: Full-Stack Loan Management System

> **This document is the authoritative mission anchor for all agents and sessions working on this project.**
> Before writing a single line of code, every agent MUST read this file completely and align all decisions to the goals defined here.

---

## 🎯 Final Product Goal

Build **LoanMaster** — a complete, production-grade, full-stack loan management platform covering the **entire lending lifecycle**:

```
[Application] → [Risk Assessment] → [Approval/Rejection] → [Disbursement] → [Repayment Tracking] → [Notifications]
```

**Target Domain:** FinTech / Lending / Credit Management
**Stack:** Python (FastAPI backend) + HTML/CSS/JS (frontend, served by FastAPI)
**Constraint:** Zero paid services. All external APIs must have free tiers or be self-hosted.

---

## 🏗️ System Domains (What Must Be Built)

### Domain 1: Loan Application Processing
- Multi-field loan application form (name, income, employment, purpose, amount, term)
- Document upload (proof of income, ID) — stored locally/in DB
- Application status lifecycle: `DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED / REJECTED → DISBURSED → ACTIVE → CLOSED / DEFAULTED`
- Full audit trail — every status change logged with timestamp and actor

### Domain 2: Risk Assessment
- **Tier 1 — Deterministic Rules (free, instant)**
  - Debt-to-Income (DTI) ratio check (>60% = auto-reject)
  - Credit score proxy heuristics based on employment, income, loan term
  - Loan-to-Income (LTI) ratio validation
- **Tier 2 — AI-Powered Underwriting (free LLM)**
  - Use **Google Gemini API** (free tier) OR **Groq API** (free tier, very fast) as primary AI underwriter
  - Structured output: `risk_score (1–100)`, `reasoning`, `decision_status`
  - Fallback chain: Gemini → Groq → Deterministic-only (no crash ever)
- Risk score stored with full reasoning memo for compliance / auditability

### Domain 3: Disbursement Tracking
- Mark approved loans as `DISBURSED` with: disbursement date, disbursed amount, payment method (bank transfer / cheque / UPI)
- Generate repayment schedule (EMI calculation) at disbursement time using standard amortization formula
- Store repayment schedule in DB as individual `Repayment` rows

### Domain 4: Repayment Tracking
- Each loan has a `RepaymentSchedule` — list of installments (due date, EMI amount, principal component, interest component)
- Record actual payments against expected installments
- Detect overdue installments (due_date < today AND status != PAID)
- Compute: outstanding principal, total paid, remaining balance, days overdue
- Late payment penalties (configurable %)

### Domain 5: Notifications
- **Email notifications** via Gmail SMTP (free, app password) OR SendGrid free tier
  - Application received confirmation
  - Risk assessment result (Approved/Rejected with reasoning)
  - Disbursement confirmation with repayment schedule
  - 3-day-before-due payment reminders
  - Overdue payment alerts
- **In-app notifications** stored in DB (notification bell on frontend)
- Scheduled background tasks (daily cron-like job) to detect due/overdue loans and trigger alerts

### Domain 6: Frontend (Full Stack)
- Single Page Application served directly by FastAPI (no separate Node server needed)
- Pages/Views:
  - **Dashboard** — KPI cards (total loans, disbursed amount, overdue count, collection rate)
  - **Applications List** — searchable, filterable, paginated table with status badges
  - **Application Detail** — full timeline view, risk assessment card, documents
  - **New Application Form** — multi-step form with validation
  - **Repayment Tracker** — per-loan installment grid, mark payments, overdue highlights
  - **Notifications Center** — in-app notification feed
- Stack: Plain HTML + Tailwind CSS (CDN) + Vanilla JS (fetch API) — no Node.js build step
- Auth: Simple JWT-based login (no OAuth for now — keep zero paid dependencies)

---

## 🛠️ Technology Stack

| Layer | Technology | Cost |
|---|---|---|
| Backend Framework | FastAPI (async) | Free |
| ORM | SQLAlchemy 2.0 async | Free |
| Database | PostgreSQL 15 (Docker) | Free |
| Migrations | Alembic | Free |
| AI Underwriter | Google Gemini API (free tier) | Free |
| AI Fallback | Groq API (free tier) | Free |
| Background Tasks | FastAPI BackgroundTasks → later Celery+Redis | Free |
| Email | SMTP (Gmail app password) + `aiosmtplib` | Free |
| Auth | python-jose (JWT) + passlib (bcrypt) | Free |
| Frontend | HTML + Tailwind CSS CDN + Vanilla JS | Free |
| Containerization | Docker Compose | Free |
| Testing | pytest + pytest-asyncio | Free |

> ⚠️ **NEVER introduce a paid service.** If a third-party integration is needed, always check for a free tier, a self-hosted alternative, or a fallback.

---

## 📦 Target Directory Structure (Final State)

```
loanpulse/
├── agentUltimatePlan.md         ← THIS FILE (read first, always)
├── skills.md                    ← Engineering patterns & conventions
├── .env                         ← Secrets (never commit)
├── .env.example                 ← Template for new devs
├── docker-compose.yml           ← Postgres + Redis (when needed)
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── config.py                ← Pydantic Settings
│   ├── database.py              ← Async engine + session
│   ├── models.py                ← ALL SQLAlchemy ORM models
│   ├── schemas.py               ← ALL Pydantic request/response schemas
│   ├── main.py                  ← FastAPI app + router includes
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py            ← User model
│   │   ├── schemas.py
│   │   ├── router.py            ← /auth/login, /auth/register
│   │   └── utils.py             ← JWT, bcrypt
│   ├── routers/
│   │   ├── applications.py      ← /applications CRUD
│   │   ├── disbursements.py     ← /disbursements
│   │   ├── repayments.py        ← /repayments
│   │   └── notifications.py     ← /notifications
│   ├── services/
│   │   ├── risk_engine.py       ← DTI rules + AI underwriting
│   │   ├── repayment_engine.py  ← EMI amortization calculator
│   │   ├── notification_service.py  ← Email + in-app notifications
│   │   └── scheduler.py         ← Cron-like background tasks
│   └── static/                  ← Served by FastAPI
│       ├── index.html
│       ├── css/
│       └── js/
│           ├── app.js
│           ├── applications.js
│           ├── repayments.js
│           └── dashboard.js
└── tests/
    ├── conftest.py
    ├── test_applications.py
    ├── test_risk_engine.py
    └── test_repayment_engine.py
```

---

## 📋 Database Schema (Target)

### `users` — Loan Officers / Admins
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| email | String UNIQUE | Login identifier |
| hashed_password | String | bcrypt |
| full_name | String | |
| role | String | `ADMIN`, `OFFICER`, `VIEWER` |
| created_at | DateTime | |
| is_active | Boolean | |

### `loan_applications` — Enhanced
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| applicant_name | String | |
| applicant_email | String | For notifications |
| applicant_phone | String | |
| employment_type | String | `SALARIED`, `SELF_EMPLOYED`, `UNEMPLOYED` |
| annual_income | Float | |
| loan_purpose | String | `HOME`, `VEHICLE`, `EDUCATION`, `PERSONAL`, `BUSINESS` |
| requested_amount | Float | |
| requested_term_months | Integer | Loan duration |
| status | String | Full lifecycle enum |
| risk_score | Integer | 1–100 |
| risk_reasoning | Text | AI memo |
| assigned_officer_id | Integer FK → users | |
| created_at | DateTime | |
| updated_at | DateTime | |

### `disbursements`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| loan_id | Integer FK → loan_applications | |
| disbursed_amount | Float | |
| interest_rate | Float | Annual % |
| disbursement_date | Date | |
| payment_method | String | `BANK_TRANSFER`, `CHEQUE`, `UPI` |
| bank_reference | String | |

### `repayment_schedule`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| loan_id | Integer FK | |
| installment_number | Integer | 1, 2, 3… |
| due_date | Date | |
| emi_amount | Float | Fixed monthly payment |
| principal_component | Float | |
| interest_component | Float | |
| status | String | `PENDING`, `PAID`, `OVERDUE`, `WAIVED` |
| paid_date | Date | Nullable |
| paid_amount | Float | Nullable (allows partial) |
| penalty_amount | Float | Default 0 |

### `audit_log`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| loan_id | Integer FK | |
| actor_id | Integer FK → users | |
| action | String | `STATUS_CHANGE`, `PAYMENT_RECORDED`, etc. |
| old_value | String | |
| new_value | String | |
| timestamp | DateTime | |
| notes | Text | |

### `notifications`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| recipient_email | String | |
| loan_id | Integer FK | Nullable |
| type | String | `EMAIL`, `IN_APP` |
| event | String | `APPLICATION_RECEIVED`, `APPROVED`, `OVERDUE`, etc. |
| subject | String | |
| body | Text | |
| sent_at | DateTime | Nullable |
| read_at | DateTime | Nullable (in-app only) |
| status | String | `PENDING`, `SENT`, `FAILED` |

---

## 🔀 Build Phases

### ✅ Phase 1 — Backend Foundation (DONE)
FastAPI + PostgreSQL + Alembic + Async SQLAlchemy + basic CRUD

### ✅ Phase 2 — AI Risk Assessment (DONE)
DTI heuristics + AI underwriter (Gemini API free tier primary, Groq fallback, deterministic DTI fast-fail)

### ✅ Phase 3 — Schema Expansion & Auth (DONE)
- Expanded `loan_applications` table with full financial & applicant lifecycle attributes
- Created `users` table + JWT authentication & bcrypt password security
- Role-based access control (RBAC): Admin, Loan Officer, Viewer
- Alembic migration `9ce96b5f5487` applied cleanly to PostgreSQL

### ✅ Phase 4 — Disbursement & Repayment Engine (DONE)
- Disbursement endpoint: validates approval, records bank reference, generates amortization schedule
- EMI amortization calculator (exact reducing balance formula with cent reconciliation)
- Store all repayment rows in `repayment_schedule` table
- Record payment endpoint with automatic status progression (ACTIVE / CLOSED)
- Overdue detection logic with penalty tracking

### ✅ Phase 5 — Notification System & Overdue Scheduler (DONE)
- Email via `aiosmtplib` + Gmail SMTP (free, with fallback logger)
- In-app notification DB (`notifications` table) + unread counter API
- Background scheduler: daily scan for due/overdue loans, emits alerts and upcoming payment reminders

### ✅ Phase 6 — Full Stack Frontend (DONE)
- FastAPI serves static files directly from `app/static/`
- Dashboard with live KPI cards (Total loans, capital disbursed, arrears count, collection rate)
- Applications pipeline table with search, status filtering, and action triggers
- Repayment servicing tracker with installment grid and payment recording
- In-app notifications feed with unread dot counter
- Session persistence with JWT auth modal

### ✅ Phase 7 — Automated Tests & Hardening (DONE)
- pytest async test suite (applications, risk engine, repayment engine, full lending lifecycle)
- Engine pool disposal fixture preventing asyncpg event loop conflicts
- Automated test coverage passing 100%

### ✅ Phase 8 — Apple Liquid Glass Theme & Responsive Mobile Ergonomics (DONE)
- Multi-layer frosted glass panels: `backdrop-filter: blur(28px) saturate(190%)`
- Specular bevel edge highlights: `border: 1px solid rgba(255, 255, 255, 0.12)` + `inset 0 1px 1px var(--glass-highlight)`
- Ambient glow mesh with luminous light orbs
- Desktop floating glass sidebar + Mobile floating bottom dock (`fixed bottom-3 left-3 right-3`)
- Google Sans & Google Sans Text typography migration across the entire site and documentation

### ✅ Phase 9 — KYC Document Storage, Detailed Audit Timeline & CSV Export (DONE)
- Local zero-cost document storage for applicant ID proof, pay slips, and bank statements (`loan_documents` table)
- Deep loan application detail modal with KYC attachments, view/download links, and inline upload
- Chronological vertical timeline of all audit events with actor attribution and notes
- 1-click amortization schedule CSV export and printable statement

---

## 🔑 API Keys & Credentials (User-Provided, Never Hardcoded)

All secrets live in `.env` and are consumed via `app/config.py` (Pydantic Settings).

| Key | Purpose | Where to Get |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection | Docker Compose |
| `GEMINI_API_KEY` | Free AI underwriter (primary) | aistudio.google.com |
| `GROQ_API_KEY` | Free AI underwriter (fallback) | console.groq.com |
| `SECRET_KEY` | JWT signing | `openssl rand -hex 32` |
| `SMTP_HOST` | Email sending | gmail smtp |
| `SMTP_PORT` | Email sending | 587 |
| `SMTP_USER` | Email sending | Gmail address |
| `SMTP_PASSWORD` | Email sending | Gmail app password |

---

## 📏 Engineering Rules (Agents MUST Follow)

1. **No paid APIs.** Gemini and Groq both have generous free tiers. Always prefer them.
2. **Alembic for every schema change.** No `create_all()` in production code paths.
3. **async everywhere.** All DB calls, HTTP calls, and email sends must be awaited. No blocking I/O.
4. **Pydantic v2 for all schemas.** Use `model_dump()`, `model_validate()`, `from_attributes=True`.
5. **No hardcoded secrets.** All secrets via `settings.*` from `.env`.
6. **Graceful degradation on AI.** If Gemini fails → try Groq → fall back to deterministic DTI rules. Never crash on AI failure.
7. **Modular routers.** Each domain has its own `routers/` file. `main.py` only includes routers, never defines routes directly.
8. **Audit every status change.** Every loan state transition must create an `audit_log` entry.
9. **Frontend served by FastAPI.** No separate Node.js server. `app/static/` folder mounted via `StaticFiles`.
10. **Free tier email only.** Gmail SMTP via `aiosmtplib` with app password is the default. Never introduce Twilio or SendGrid paid tiers.

---

## 🧭 For Any Future Agent Starting a Session

Read the following in order:
1. **This file** (`agentUltimatePlan.md`) — understand the mission & architecture
2. **`alreadyDone.md`** — see exact record of what has been built and tested
3. **`toDo.md`** — check current tasks or scale enhancements
4. **`app/models.py`** — understand database schema
5. **Run test suite**: `venv/bin/pytest tests/ -v`

---

*Last updated: 2026-10-19. All Core Phases (1 through 9) are 100% complete and operational.*
