# LoanPulse: Phase 1 Backend Initialization

> Historical phase instructions for the original FastAPI prototype. The current runtime uses Django; do not use the commands or stack below as the current runbook. See [README.md](README.md).

> Historical implementation notes. The maintained application now uses Django and DATABASE_URL; Docker and this FastAPI/Alembic setup are no longer used. Follow [README.md](README.md) to run the current app.

# Objective (historical): Build an asynchronous FastAPI backend connected to PostgreSQL via Docker, managed by Alembic migrations.

## Project Structure
Please initialize the following directory structure:
```text
loanpulse/
├── .env
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── alembic/
│   └── env.py
└── app/
    ├── __init__.py
    ├── config.py
    ├── database.py
    ├── models.py
    ├── schemas.py
    └── main.py
```

## Step 1: Dependencies and Environment (`requirements.txt` & `.env`)

### `requirements.txt`
```text
fastapi
uvicorn[standard]
sqlalchemy
pydantic
pydantic-settings
asyncpg
alembic
```

### `.env`
```text
DATABASE_URL=postgresql+asyncpg://admin:secretpassword@localhost:5432/loanpulse_db
```

## Step 2: Docker Database Setup (`docker-compose.yml`)
```yaml
version: '3.8'
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secretpassword
      POSTGRES_DB: loanpulse_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Step 3: Application Code

### `app/config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str

    class Config:
        env_file = ".env"

settings = Settings()
```

### `app/database.py`
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

engine = create_async_engine(settings.database_url, echo=True)

AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session
```

### `app/models.py`
```python
from sqlalchemy import Column, Integer, String, Float
from app.database import Base

class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id = Column(Integer, primary_key=True, index=True)
    applicant_name = Column(String, index=True)
    annual_income = Column(Float)
    requested_amount = Column(Float)
    status = Column(String, default="PENDING")
```

### `app/schemas.py`
```python
from pydantic import BaseModel, Field
from typing import Optional

class LoanApplicationBase(BaseModel):
    applicant_name: str = Field(..., min_length=2, max_length=100)
    annual_income: float = Field(..., gt=0)
    requested_amount: float = Field(..., gt=0)

class LoanApplicationCreate(LoanApplicationBase):
    pass

class LoanStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(PENDING|UNDER_REVIEW|APPROVED|REJECTED)$")

class LoanApplicationResponse(LoanApplicationBase):
    id: int
    status: str

    class Config:
        from_attributes = True
```

### `app/main.py`
```python
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import engine, Base, get_async_db
from app.models import LoanApplication
from app.schemas import LoanApplicationCreate, LoanApplicationResponse, LoanStatusUpdate

app = FastAPI(title="LoanPulse API", version="0.2.0")

@app.post("/applications/", response_model=LoanApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(application: LoanApplicationCreate, db: AsyncSession = Depends(get_async_db)):
    db_loan = LoanApplication(**application.model_dump())
    db.add(db_loan)
    await db.commit()
    await db.refresh(db_loan)
    return db_loan

@app.get("/applications/", response_model=List[LoanApplicationResponse])
async def list_applications(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(LoanApplication).offset(skip).limit(limit))
    return result.scalars().all()

@app.get("/applications/{application_id}", response_model=LoanApplicationResponse)
async def get_application(application_id: int, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(LoanApplication).where(LoanApplication.id == application_id))
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return loan

@app.patch("/applications/{application_id}/status", response_model=LoanApplicationResponse)
async def update_application_status(application_id: int, payload: LoanStatusUpdate, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(LoanApplication).where(LoanApplication.id == application_id))
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")
    
    loan.status = payload.status
    await db.commit()
    await db.refresh(loan)
    return loan
```

## Step 4: Alembic Configuration

**Agent Instructions for running Alembic:**
1. Run `alembic init -t async alembic` in the root directory to generate the asynchronous template files.
2. Modify the generated `alembic/env.py` to import settings and models. Replace the top portion of `alembic/env.py` with the following:

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import settings and models
from app.config import settings
from app.database import Base
from app.models import LoanApplication 

config = context.config

# Override sqlalchemy.url with our settings string
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata
target_metadata = Base.metadata
```

## Execution Commands
After building the files, the agent should run these commands in the terminal:
```bash
# 1. Start the database
docker compose up -d

# 2. Generate the initial migration
alembic revision --autogenerate -m "create loan application table"

# 3. Apply the migration to the database
alembic upgrade head

# 4. Start the server
uvicorn app.main:app --reload
```
