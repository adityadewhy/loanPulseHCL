# LoanPulse

LoanPulse is a Django loan origination and servicing app. Borrowers apply for loans and track decisions; staff review and service applications. PostgreSQL stores accounts and loan data. Uploaded documents use local disk storage by default.

## Workflows

### Borrowers

Create a borrower account in the sign-in screen, submit a loan request, and use **My loan applications** to track its status and repayment schedule. KARZai answers loan-related questions only.

### Staff

Choose **Staff** during signup. Staff accounts stay inactive until the boss approves them. The boss signs in and uses **Staff registrations** to review pending requests, browse approved or disapproved requests, and change or revert a decision. Approved staff can review loan applications and perform servicing actions according to their role.

## Run locally

Requirements: Python 3.12+, Node.js 22, and a PostgreSQL database (Neon works).

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
npm ci
cp .env.example .env
```

Set a unique `SECRET_KEY`, a PostgreSQL `DATABASE_URL`, and the `BOSS_EMAIL` / `BOSS_PASSWORD` credentials in `.env`. Keep `.env` private. Build the frontend stylesheet, create the database schema, provision the boss login, and start Django:

```sh
npm run build:css
python manage.py migrate
python manage.py create_admin
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000). For production, use Gunicorn behind a TLS-terminating reverse proxy. The app reads `DATABASE_URL` from the process environment or `.env`; Neon pooled connections should set `DISABLE_SERVER_SIDE_CURSORS=true`.

Production application command: `gunicorn config.wsgi:application --bind 127.0.0.1:8000`.

## AI and privacy

Loan-to-income rules run first. When configured, AI underwriting receives only annual income, requested amount, and their ratio; model results are advisory and a staff member makes approval decisions. KARZai applies a loan-topic filter, rate limit, short output cap, and local answers for product details the app does not publish. Optional KYC document quality checks require borrower consent and are not identity verification.

## Operations

- Configure `ALLOWED_HOSTS`, HTTPS proxy settings, secure cookies, and HSTS before public deployment.
- PostgreSQL stores passwords as hashes. Back up PostgreSQL and the uploads directory; Neon does not store uploaded documents.
- Borrower signup validates email syntax but does not verify mailbox ownership. Notifications are in-app; email delivery is not configured.
- Run the Django migration command after code updates.

## Verification

The test suite uses SQLite and mocks external AI providers:

```sh
DATABASE_URL=sqlite:////tmp/loanpulse-tests.sqlite3 .venv/bin/pytest -q
node --check app/static/app.js
npm run build:css
python manage.py check --deploy
```
