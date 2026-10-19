# LoanPulse — Current Product and Architecture

Last updated: 2026-10-20

This document describes the current implementation. Earlier phase notes remain in the repository as historical records; use [README.md](README.md) and this file for current setup and behavior.

## Product goal

LoanPulse serves two distinct roles in one application:

- **Borrowers (`CUSTOMER`)** create an account, request supported loan types, optionally attach documents, and track their own application status and repayment schedule.
- **Staff (`ADMIN`, `OFFICER`, `VIEWER`)** manage the portfolio. Admins and officers can originate or review applications, record decisions, disburse approved loans, service repayments, and manage documents. Viewers have read-only portfolio access.

Self-service registration always creates a borrower. Staff roles are provisioned by an administrator. Backend ownership checks are authoritative; hiding UI controls is only a usability measure.

## Loan lifecycle

```text
Borrower account → Application → Risk/rules assessment → Staff decision
                 → Disbursement → Repayment schedule → Servicing → Closed
```

Risk assessment can use Gemini, then Groq, then deterministic rules. Provider responses are validated and advisory. Borrower feedback reuses that assessment request; it never makes an extra model call or promises approval or a review time. An institution-configured loan-to-income rejection policy may reject an application automatically; AI output cannot approve one.

Borrowers can also use KARZai for loan-only support. Local FAQ answers handle rates and review timing without Gemini when LoanPulse has no published values. Other questions must pass a strict word allowlist and are sent without chat history or account data, with request throttling, output limits, and a 24-hour answer cache. Borrower-selected KYC files can receive an optional, explicit-consent preliminary quality check; documents are sent to Gemini only on request, and the result is neither stored nor used as an identity or credit decision.

Supported loan types are home, vehicle, education, personal, and business. Money calculations use `Decimal` and cent-level schedule reconciliation.

## Current stack

| Layer | Implementation |
|---|---|
| Backend | Django 5.2, Django REST Framework |
| Database | PostgreSQL, Django ORM and migrations |
| Authentication | Django password hashing and signed 12-hour JWT bearer tokens |
| Frontend | Django-served HTML, JavaScript, and compiled Tailwind CSS |
| Runtime | Django, Gunicorn, WhiteNoise; PostgreSQL via DATABASE_URL |
| AI | Optional Gemini and Groq providers with deterministic fallback |
| Tests | pytest, pytest-django, isolated SQLite integration tests |

## Data access boundaries

- Borrower accounts own applications through `LoanApplication.applicant_user`.
- Borrower list, detail, count, dashboard, notification, disbursement, repayment, export, and document queries are scoped to that owner.
- Borrower serializers omit internal risk reasoning, risk scores, officer assignments, and staff audit notes.
- Borrowers can submit supporting documents for their applications and download only their own files. Staff document deletion remains staff-only.
- Staff users can inspect the portfolio; only admins and officers can make workflow changes.
- KARZai and its optional KYC review are borrower-only, throttled, and ownership-scoped. KYC review requires affirmative consent and a supported file type/size.
- Existing applications remain staff-visible after migration unless the migration can associate them with an existing `CUSTOMER` account by email. New borrower access is linked to account ownership in the database, not by names supplied to requests.

## Project structure

- `config/`: Django settings, URL routing, WSGI/ASGI configuration.
- `loanpulse_app/`: models, APIs, services, permissions, and Django migrations.
- `app/static/`: UI source; `frontend/` and Tailwind config build the stylesheet.
- `tests/test_django_app.py`: API, workflow, access-control, AI-boundary, and repayment tests.
- `README.md`: setup and user workflows.
- `skills.md`: current engineering conventions.
- `toDo.md`: delivery status and deployment follow-ups.

## Operations

Configure `DATABASE_URL` and the boss credentials in `.env`, run migrations, create the boss account with `python manage.py create_admin`, and run Django/Gunicorn directly. For TLS, set the reverse-proxy and cookie settings documented in `.env.example` after validating the host configuration.

Run tests with `DATABASE_URL=sqlite:////tmp/loanpulse-tests.sqlite3 .venv/bin/pytest -q`. External AI requests are mocked in the test suite; do not put real provider credentials in test fixtures or source control.

## Deployment follow-ups

See [toDo.md](toDo.md) for items that depend on the customer institution or hosting environment, including mailbox verification, jurisdiction-specific lending policy, KYC document privacy approval, TLS, backups, monitoring, and file malware scanning.
