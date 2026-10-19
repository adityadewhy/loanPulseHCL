# LoanPulse — Engineering Skills & Conventions Reference

> This document captures the engineering patterns, conventions, and skills used across this codebase.
> Every agent and developer should read this alongside `agentUltimatePlan.md` before writing code.

---

## 1. Project Setup & Environment

### Virtual Environment
- **Active venv:** `./venv/` (Python 3.14) — this is the primary, contains all dependencies.
- **Activate:** `source venv/bin/activate` (or prefix commands with `venv/bin/`)
- **Install deps:** `venv/bin/pip install -r requirements.txt`

### Running the Server
```bash
# Development (hot reload)
venv/bin/uvicorn app.main:app --reload --port 8000

# Production-style
venv/bin/uvicorn app.main:app --port 8000 --workers 4
```

### Docker Database
```bash
# Start Postgres 15 container
echo "docker compose up -d" | newgrp docker

# Connect directly to inspect
echo "docker exec loanpulse-db-1 psql -U admin -d loanpulse_db -c 'SELECT * FROM loan_applications;'" | newgrp docker
```

> ⚠️ The current user (`adirchy`) is in the `docker` group but the session token hasn't refreshed. Use `| newgrp docker` to pipe docker commands, or log out and back in.

---

## 2. Async SQLAlchemy Patterns

### Engine & Session Factory (app/database.py)
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_async_engine(settings.database_url, echo=True)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False   # CRITICAL: prevents MissingGreenlet errors in async
)

Base = declarative_base()

async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session            # yield, not return — guarantees cleanup
```

### Why `expire_on_commit=False`?
In async SQLAlchemy, attributes are marked "expired" after `commit()`. Reading them later triggers a lazy load, which requires a synchronous DB round-trip that is **illegal in async context** (raises `MissingGreenlet`). With `expire_on_commit=False`, committed values stay in memory.

### The Dependency Injection Pattern
```python
# Route handler receives a session, automatically closed when request ends
@router.post("/applications/")
async def create_app(data: LoanCreate, db: AsyncSession = Depends(get_async_db)):
    ...
```

### Query Patterns (SQLAlchemy 2.0 style — always use this)
```python
# SELECT
result = await db.execute(select(LoanApplication).where(LoanApplication.id == loan_id))
loan = result.scalar_one_or_none()

# SELECT with filter + order
result = await db.execute(
    select(LoanApplication)
    .where(LoanApplication.status == "PENDING")
    .order_by(LoanApplication.created_at.desc())
    .limit(10)
)

# COUNT
from sqlalchemy import func
result = await db.execute(select(func.count(LoanApplication.id)))
count = result.scalar()
```

---

## 3. Alembic Migration Workflow

> **Rule: Every schema change = a new Alembic revision. Never use `Base.metadata.create_all()` in production.**

```bash
# 1. Update app/models.py with the schema change
# 2. Autogenerate the migration
venv/bin/alembic revision --autogenerate -m "describe your change"

# 3. Review the generated file in alembic/versions/
# 4. Apply to the database
venv/bin/alembic upgrade head

# 5. Verify
venv/bin/alembic current
```

### Why Alembic?
- `create_all()` only creates new tables — it cannot add columns, change types, or drop fields.
- Alembic tracks a DAG of revisions in the `alembic_version` table inside PostgreSQL.
- Each migration has `upgrade()` and `downgrade()` — rollback is always possible.

### Checking Migration History
```bash
venv/bin/alembic history --verbose
venv/bin/alembic current
venv/bin/alembic downgrade -1   # Roll back one step
```

---

## 4. Pydantic v2 Schema Patterns

### Request / Response Separation
```python
# Base shared fields
class LoanBase(BaseModel):
    applicant_name: str = Field(..., min_length=2, max_length=100)
    annual_income: float = Field(..., gt=0)

# Create request (what client sends)
class LoanCreate(LoanBase):
    pass

# Response (what API returns) — ALWAYS include from_attributes
class LoanResponse(LoanBase):
    id: int
    status: str
    risk_score: Optional[int] = None

    class Config:
        from_attributes = True   # Allows ORM object → Pydantic conversion
```

### Useful Validators
```python
from pydantic import field_validator, model_validator

@field_validator("status")
@classmethod
def validate_status(cls, v):
    allowed = {"PENDING", "APPROVED", "REJECTED"}
    if v not in allowed:
        raise ValueError(f"status must be one of {allowed}")
    return v
```

### Regex Pattern Validation
```python
status: str = Field(..., pattern="^(PENDING|UNDER_REVIEW|APPROVED|REJECTED)$")
```

---

## 5. FastAPI Router Structure

### Adding a New Domain (e.g. Disbursements)
```python
# app/routers/disbursements.py
from fastapi import APIRouter
router = APIRouter(prefix="/disbursements", tags=["Disbursements"])

@router.post("/")
async def create_disbursement(...):
    ...

# app/main.py
from app.routers import disbursements
app.include_router(disbursements.router)
```

### Background Tasks Pattern
```python
@router.post("/applications/")
async def create_application(
    data: LoanCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    loan = LoanApplication(**data.model_dump())
    db.add(loan)
    await db.commit()
    await db.refresh(loan)

    # Dispatch non-blocking background work
    background_tasks.add_task(evaluate_loan_risk, loan.id, db)

    return loan  # Returns immediately as PENDING
```

---

## 6. AI Integration (Free Providers)

### Provider Priority Chain
```
1. Google Gemini (free tier: gemini-1.5-flash)
2. Groq (free tier: llama-3.1-8b-instant or mixtral)
3. Deterministic DTI-only fallback (always works, no API needed)
```

### Gemini (google-generativeai SDK)
```python
import google.generativeai as genai
genai.configure(api_key=settings.gemini_api_key)

model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content(prompt)
```

### Groq (openai-compatible SDK)
```python
from groq import AsyncGroq
client = AsyncGroq(api_key=settings.groq_api_key)

completion = await client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role": "user", "content": prompt}],
    response_format={"type": "json_object"}
)
```

### Graceful Fallback Chain
```python
async def evaluate_loan_risk(loan_id, db):
    dti = loan.requested_amount / loan.annual_income
    if dti > 0.60:
        return await _apply_auto_reject(loan, db)

    try:
        return await _gemini_evaluate(loan, db)
    except Exception as e:
        print(f"Gemini failed: {e}")

    try:
        return await _groq_evaluate(loan, db)
    except Exception as e:
        print(f"Groq failed: {e}")

    await _deterministic_fallback(loan, dti, db)
```

---

## 7. EMI Amortization Formula

Standard reducing-balance (equal monthly installment) formula used by all banks:

```
Monthly Rate (r) = annual_interest_rate / 12 / 100
EMI = P × r × (1 + r)^n / ((1 + r)^n - 1)

Where:
  P = Principal (disbursed_amount)
  r = Monthly interest rate
  n = Number of installments (term_months)
```

### Python Implementation
```python
def calculate_emi(principal: float, annual_rate: float, term_months: int) -> float:
    r = annual_rate / 12 / 100
    if r == 0:
        return principal / term_months
    return principal * r * (1 + r)**term_months / ((1 + r)**term_months - 1)

def generate_amortization_schedule(principal, annual_rate, term_months, start_date):
    emi = calculate_emi(principal, annual_rate, term_months)
    balance = principal
    schedule = []
    for i in range(1, term_months + 1):
        interest = balance * annual_rate / 12 / 100
        principal_component = emi - interest
        balance -= principal_component
        schedule.append({
            "installment_number": i,
            "due_date": start_date + relativedelta(months=i),
            "emi_amount": round(emi, 2),
            "principal_component": round(principal_component, 2),
            "interest_component": round(interest, 2),
        })
    return schedule
```

---

## 8. Email Notifications (aiosmtplib — Free)

### Setup
```bash
pip install aiosmtplib
```

### Usage Pattern
```python
import aiosmtplib
from email.message import EmailMessage

async def send_email(to: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,    # "smtp.gmail.com"
        port=settings.smtp_port,        # 587
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )
```

### Gmail App Password Setup
1. Enable 2FA on Gmail account
2. Go to Google Account → Security → App Passwords
3. Create "Mail" app password → copy the 16-char password
4. Set `SMTP_PASSWORD=<app_password>` in `.env`

---

## 9. JWT Authentication Pattern

```python
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=24)):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")

def verify_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
```

### FastAPI Auth Dependency
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = await db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

---

## 10. Frontend Patterns (Served by FastAPI)

### Static File Mounting
```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("app/static/index.html")
```

### Fetch API Pattern (Vanilla JS)
```javascript
async function loadApplications() {
    const token = localStorage.getItem("access_token");
    const res = await fetch("/applications/", {
        headers: { "Authorization": `Bearer ${token}` }
    });
    const data = await res.json();
    renderApplications(data);
}
```

### Status Badge Color Map
```javascript
const STATUS_COLORS = {
    PENDING:      "bg-yellow-100 text-yellow-800",
    UNDER_REVIEW: "bg-blue-100 text-blue-800",
    APPROVED:     "bg-green-100 text-green-800",
    REJECTED:     "bg-red-100 text-red-800",
    DISBURSED:    "bg-purple-100 text-purple-800",
    ACTIVE:       "bg-emerald-100 text-emerald-800",
    CLOSED:       "bg-gray-100 text-gray-800",
    DEFAULTED:    "bg-rose-100 text-rose-800",
};
```

---

## 11. Testing Patterns

### pytest-asyncio Setup
```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

### Test Template
```python
@pytest.mark.asyncio
async def test_create_application_success(async_client):
    response = await async_client.post("/applications/", json={
        "applicant_name": "Test User",
        "annual_income": 80000,
        "requested_amount": 20000,
        "requested_term_months": 24,
    })
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
```

---

## 12. Useful Commands Reference

```bash
# Check what's in the database
echo "docker exec loanpulse-db-1 psql -U admin -d loanpulse_db -c '\dt'" | newgrp docker
echo "docker exec loanpulse-db-1 psql -U admin -d loanpulse_db -c '\d loan_applications'" | newgrp docker

# Run migrations
venv/bin/alembic revision --autogenerate -m "description"
venv/bin/alembic upgrade head
venv/bin/alembic current
venv/bin/alembic history

# Run tests
venv/bin/pytest tests/ -v

# Start server
venv/bin/uvicorn app.main:app --reload --port 8000

# Quick API test
curl -s -X POST http://127.0.0.1:8000/applications/ \
  -H "Content-Type: application/json" \
  -d '{"applicant_name": "Test User", "annual_income": 80000, "requested_amount": 20000}'
```

---

## 13. Known Issues & Gotchas

| Issue | Root Cause | Fix |
|---|---|---|
| `docker ps` permission denied | User in docker group but session not refreshed | Use `echo "docker ..." \| newgrp docker` |
| `MissingGreenlet` error | Accessing expired SQLAlchemy attribute after `commit()` in async context | Always use `expire_on_commit=False` in `sessionmaker` |
| Alembic generates empty `pass` migration | Columns already exist in DB from a previous run | Check `alembic current` and existing schema; delete the empty revision file |
| OpenAI 401 error | `your_openai_api_key_here` placeholder in `.env` | Replace with real key, or switch to Gemini/Groq (free) |

---

*This file should be updated whenever a new pattern, convention, or gotcha is discovered.*
