# LoanPulse — Engineering Conventions

Last updated: 2026-10-20

The runtime is Django. Older FastAPI/Alembic notes in phase documents are historical and should not be used as implementation instructions.

## Local setup

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
npm ci
cp .env.example .env
```

Configure PostgreSQL and `SECRET_KEY` in `.env`. Build and serve locally with:

```sh
npm run build:css
python manage.py migrate --fake-initial
python manage.py runserver
```

Use Django's local development server and Gunicorn for deployment. PostgreSQL is configured by DATABASE_URL. See [README.md](README.md).

## Django and API patterns

- Put persistent data access in Django models and use migrations for schema changes. Never edit an applied migration; create a new migration and review it.
- Keep API request validation separate from model persistence with DRF serializers.
- Keep external AI calls outside open database transactions. Validate provider output before writing it.
- Use `transaction.atomic()` around multi-row money/status changes and lock rows where concurrent writes could double-disburse or double-pay.
- Return minimal role-specific response data. A borrower query must be filtered by `applicant_user` on the server before serialization.
- Use `get_object_or_404()` with an owner-scoped queryset to avoid leaking whether another borrower's resource exists.
- Treat UI visibility as presentation only. Enforce the same role and ownership rules in the API.
- Prefer database constraints for invariants that can be expressed in SQL. Keep exact-cent financial calculations in `Decimal`, not binary floating point.

## Roles and workflows

- `ADMIN`: portfolio access, staff provisioning, and all write workflows.
- `OFFICER`: portfolio review, decisions, disbursement, servicing, and document handling.
- `VIEWER`: read-only portfolio access.
- `CUSTOMER`: self-service borrower account. May submit applications and documents and read only its owned applications, notifications, documents, and schedules.
- Public registration must create `CUSTOMER` only. Staff accounts are created by an admin or the bootstrap command.
- Never accept applicant identity, ownership, assigned officer, risk result, or status from a borrower request when those values are derived or controlled by the server.

## Security and operations

- Keep secrets in ignored `.env` or deployment secret storage. Never commit real API keys, passwords, or customer data.
- Use Django password hashing and validators; do not log credentials, document contents, provider prompts, or provider responses.
- Keep uploaded files outside static assets, enforce extension/MIME/size checks, and check ownership on upload and download.
- Configure HTTPS at the deployment proxy. Trust forwarded protocol headers only from a proxy that overwrites them.
- Keep loan and notification reads scoped. Do not add a new endpoint that returns a global queryset to the borrower role.
- AI results are advisory; policy thresholds and staff workflow remain explicit and testable.
- For borrower AI chat, reject out-of-domain text before any provider call. Keep rate/SLA answers grounded in configured LoanPulse facts; never fill unpublished values from model memory.
- Never send a borrower document to an AI provider without an explicit user action and clear disclosure. Keep document review preliminary and non-decisional, scope it to the owner's document, and exclude extracted personal values from returned or persisted output.
- Bound provider input/output, apply per-user throttling, and cache repeated FAQ/document results where appropriate to limit cost.

## AI provider boundary

Provider adapters should be isolated in `loanpulse_app/services.py`, use bounded timeouts, accept only the minimum facts needed, parse structured JSON, validate responses, and fail over without failing application creation. Underwriting must not send names/contact details/files. KARZai must not send chat history or account data. KYC file transmission must remain explicit opt-in. Unit tests should mock provider SDK boundaries; no real provider key is needed to run tests.

## Frontend conventions

- Keep the staff and borrower experiences separate. Borrower views should show only borrower-safe fields and actions.
- Escape user-controlled strings in HTML templates or assign them with `textContent`.
- Never put bearer tokens in `localStorage`; the current UI uses `sessionStorage`.
- Keep Tailwind source/build steps in `package.json`; do not hand-edit generated `app/static/tailwind.css`.
- Run `node --check app/static/app.js` and `npm run build:css` after UI changes.

## Verification commands

```sh
DATABASE_URL=sqlite:////tmp/loanpulse-tests.sqlite3 .venv/bin/pytest -q
node --check app/static/app.js
npm run build:css
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

For borrower changes, include tests proving that one borrower cannot access another borrower's application, notifications, documents, or repayment data. For staff changes, keep the admin/officer lifecycle covered.
