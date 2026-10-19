# LoanPulse — Delivery Status and Follow-up Work

Last updated: 2026-10-20

## Delivered

- [x] Django 5.2 REST backend, PostgreSQL models/migrations, and Gunicorn runtime without Docker dependency.
- [x] Neon-compatible DATABASE_URL configuration and staff signup approval workflow for the boss account.
- [x] Staff workflow: portfolio dashboard, application review, AI/rules assessment, status decisions, disbursement, repayment servicing, documents, notifications, and audit history.
- [x] Borrower workflow: public borrower-only sign-up, loan requests for home/vehicle/education/personal/business products, optional document upload, personal status history, and own repayment schedule.
- [x] Role and ownership checks restrict borrowers to their own application data and prevent self-registration as staff.
- [x] Security improvements include password validation, signup throttling, advisory AI policy, and no automatic late fee when an installment becomes overdue.
- [x] Markdown runbooks and architecture notes updated to describe the Django application.
- [x] Add borrower-only KARZai with a strict pre-model loan-topic filter, local answers for rates and review times, throttling, bounded output, and answer caching.
- [x] Reuse underwriting output for borrower feedback after submission; do not make a second model call or predict approval/timing.
- [x] Add consent-based, on-demand preliminary KYC document quality review with borrower ownership checks, file limits, throttling, caching, and no automated KYC or credit decision.

## Before a public client rollout

- [ ] Add email ownership verification if verified contact identity is required by the deployment.
- [ ] Complete borrower-facing browser end-to-end checks on supported browsers and mobile sizes.
- [ ] Configure TLS/reverse proxy, production secrets, backups, monitoring, and HSTS for the hosting environment.
- [ ] Confirm loan product, underwriting, privacy, document-retention, and repayment policies with the operating institution and applicable jurisdiction.
- [ ] Review privacy notice and provider terms for sending borrower-selected KYC documents to Google Gemini before enabling this optional feature in a live deployment.
- [ ] Add malware scanning and retention controls if uploaded documents are accepted in a public deployment.

## Run and verify

```sh
# Django app and schema
python manage.py migrate --fake-initial
python manage.py runserver

# Backend and AI-path tests (provider APIs are mocked)
DATABASE_URL=sqlite:////tmp/loanpulse-tests.sqlite3 .venv/bin/pytest -q

# Frontend source and styles
node --check app/static/app.js
npm run build:css

# Production configuration check
python manage.py check --deploy
```

See [README.md](README.md) for local setup, environment variables, and borrower/staff workflows.
