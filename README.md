# 💳 LoanPulse: LoanMaster Loan Management System

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://www.postgresql.org)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-orange.svg)](https://alembic.sqlalchemy.org)
[![License](https://img.shields.io/badge/Cost-100%25%20Free%20Tier-success.svg)]()

**LoanPulse** is an enterprise-grade, full-stack loan management and credit lifecycle platform built in Python (FastAPI async backend) and served directly via a high-performance modern Single Page Application (SPA).

It implements the entire consumer and SME lending lifecycle:
```
[Application & KYC] ➔ [AI Risk Underwriting] ➔ [Approval/Rejection] ➔ [Disbursement] ➔ [Amortization & Repayments] ➔ [Notifications & Arrears Engine]
```

> 💡 **Zero Paid Services Policy**: Every service used in LoanPulse is 100% free-tier, self-hosted, or open-source (Google Gemini free-tier underwriting, local PostgreSQL in Docker, local filesystem KYC storage, and standard SMTP).

---

## 🌟 Core Feature Domains

### 1. Loan Application & KYC Document Processing
- Multi-field origination form with automated client validation and financial triage.
- **Zero-Cost KYC Document Attachment System**: Local disk storage with database metadata tracking for applicant passport scans, pay slips, and bank statements (`.pdf`, `.png`, `.jpg`, `.webp` up to 15MB).
- Real-time Debt-to-Income (DTI) live calculator meter on applicant intake.

### 2. Autonomous AI Risk Underwriting & Triage
- **Tier 1 — DTI Fast-Fail Heuristic**: Instant rejection if DTI exceeds 60% (no API tokens consumed).
- **Tier 2 — Google Gemini API Free-Tier LLM**: Multi-factor credit memo with calibrated risk score (1–100) and structured decision reasoning.
- **Tier 3 — Graceful Degradation**: Fallback to deterministic rules if external LLM quotas are exhausted; API never crashes.

### 3. Disbursement Engine & Reducing-Balance Amortization
- Validates loan approval and prevents duplicate disbursements.
- Computes monthly Equated Monthly Installments (EMI) using exact financial reducing-balance amortization with cent-reconciliation.
- Automatically generates discrete installment schedules in PostgreSQL.

### 4. Repayment Servicing & Arrears Management
- Installment servicing and partial/full payment tracking.
- Automatic loan lifecycle status updates (`ACTIVE` ➔ `CLOSED` on completion).
- Overdue scanner applying 2% penalty fees on defaulted schedules.
- **1-Click Amortization CSV Export** and browser print statements.

### 5. Notification System & Chronological Audit Logging
- Email dispatch via `aiosmtplib` with Gmail SMTP and safe fallback logger.
- In-app notification feed with live unread counter.
- Full compliance audit trail: every status transition, payment, and KYC upload is immutably timestamped with actor attribution.

### 6. Apple Liquid Glass UI Design & Dual-Screen Ergonomics
- Frosted translucent glass panels (`backdrop-filter: blur(28px) saturate(190%)`) with specular perimeter highlights.
- **Dual-Screen Layout Strategy**:
  - **Desktop / Laptop (`>1024px`)**: Sleek floating glass sidebar (`w-72`), widescreen KPI cards, deep application detail modals.
  - **Mobile Phone (`<1024px`)**: Floating bottom glass dock (`fixed bottom-3 left-3 right-3`), touch-safe padding (`pb-28`), horizontal scroll tables.
- **Google Sans Typography**: Clean, modern typography across all screens and dashboards.

---

## 🛠️ Technology Stack

| Layer | Component | Notes |
|---|---|---|
| **Backend** | FastAPI (async) | High-concurrency Python 3.14 async ASGI framework |
| **Database** | PostgreSQL 15 | Running in isolated Docker Compose container |
| **ORM** | SQLAlchemy 2.0 (asyncio) | Fully typed async sessions with asyncpg driver |
| **Schema Migrations** | Alembic | Complete revision history in `alembic/versions/` |
| **Authentication** | JWT + bcrypt | Stateless bearer tokens, direct bcrypt password security |
| **AI Underwriting** | Google Gemini API | Free-tier LLM credit risk reasoning |
| **KYC Storage** | Local Disk Storage (`uploads/`) | Zero-cost persistent file store with UUID sanitization |
| **Frontend** | Tailwind CSS CDN + Vanilla JS | Single Page App served directly via FastAPI StaticFiles |
| **Testing** | pytest + pytest-asyncio | 9/9 automated tests passing with connection disposal |

---

## 📂 Project Architecture

```
loanpulse/
├── agentUltimatePlan.md         # Master blueprint and requirements anchor
├── alreadyDone.md               # Detailed history of completed phases (1-9)
├── toDo.md                      # Next tasks & production scale enhancements
├── skills.md                    # Engineering standards & code conventions
├── docker-compose.yml           # PostgreSQL database container
├── pytest.ini                   # Pytest configuration
├── alembic.ini                  # Alembic migration configuration
├── alembic/versions/            # Database schema migration scripts
├── app/
│   ├── main.py                  # FastAPI entry point & router mounting
│   ├── config.py                # Pydantic Settings & environment variables
│   ├── database.py              # Async SQLAlchemy engine & session factory
│   ├── models.py                # 7 Database ORM models
│   ├── schemas.py               # Pydantic v2 request/response schemas
│   ├── auth/                    # JWT authentication & password hashing
│   ├── routers/                 # Modular domain routers
│   │   ├── applications.py      # Loan intake, details, and status updates
│   │   ├── disbursements.py     # Loan capital disbursement
│   │   ├── repayments.py        # EMI servicing & CSV export
│   │   ├── documents.py         # KYC file upload, list, download, delete
│   │   ├── notifications.py     # In-app alerts & read receipts
│   │   └── dashboard.py         # Real-time portfolio KPI metrics
│   ├── services/                # Business logic engines
│   │   ├── risk_engine.py       # Multi-tier AI & DTI risk evaluation
│   │   ├── repayment_engine.py  # EMI calculation & schedule generator
│   │   ├── notification_service.py # Email & DB notifications
│   │   └── scheduler.py         # Periodic arrears scanner
│   └── static/                  # Apple Liquid Glass Frontend SPA
│       ├── index.html           # Responsive HTML interface
│       └── app.js               # Reactive vanilla JS frontend logic
├── uploads/                     # Local KYC document storage
└── tests/                       # Pytest automated test suite (9 tests)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Linux or macOS system
- Python 3.11+ (Python 3.14 verified)
- Docker & Docker Compose

### 2. Start PostgreSQL Database
```bash
docker compose up -d
```
*PostgreSQL will be accessible on `localhost:5432` with database `loanpulse_db`.*

### 3. Configure Environment Variables
Copy the template environment file:
```bash
cp .env.example .env
```
*(Optional: Add your free Google Gemini API key from Google AI Studio to `.env` for AI underwriting; the system automatically falls back to deterministic DTI underwriting rules if not configured).*

### 4. Install Python Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Run Database Migrations
```bash
venv/bin/alembic upgrade head
```

### 6. Launch the Development Server
```bash
venv/bin/uvicorn app.main:app --reload --port 8000
```

### 7. Access the Application
Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

**Default Administrator Credentials**:
- **Email**: `admin@loanpulse.local`
- **Password**: `Admin123!`

---

## 🧪 Running Automated Tests

Run the full pytest integration test suite:
```bash
venv/bin/pytest tests/ -v
```

All 9 automated test suites verify:
- Complete end-to-end lending lifecycle (apply ➔ approve ➔ disburse ➔ pay ➔ audit)
- EMI amortization formula reducing-balance reconciliation
- DTI fast-fail thresholds (auto-reject >60%)
- KYC file upload, download, and physical deletion
- CSV amortization schedule generation and header verification

---

## 📊 Interactive Learning Dashboards

LoanPulse includes built-in interactive HTML dashboards to learn the engineering principles behind the code:
- **Liquid Glass & Responsive Design Guide**: Open [`glass_learning_dashboard.html`](glass_learning_dashboard.html) in any browser to explore interactive glass physics sliders and dual-screen design principles.
- **Phase 1 Backend Foundation Guide**: Open [`phase1_learning_dashboard.html`](phase1_learning_dashboard.html).
- **Phase 2 AI Risk Underwriting Guide**: Open [`phase2_learning_dashboard.html`](phase2_learning_dashboard.html).

---

## 📜 License
Developed as an open, free-tier FinTech reference implementation.
