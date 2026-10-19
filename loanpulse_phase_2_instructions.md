# LoanPulse: Phase 2 AI Risk Scoring & Automated Rules

# Objective: Evolve the database to store risk metrics, integrate a financial heuristic (DTI ratio), and use OpenAI for automated underwriting via FastAPI background tasks.

## Step 1: Database Schema Evolution

We need to store the AI's evaluation results. 

1. **Update `app/models.py`:** Add two new columns to the `LoanApplication` model.
```python
# app/models.py
from sqlalchemy import Column, Integer, String, Float
from app.database import Base

class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id = Column(Integer, primary_key=True, index=True)
    applicant_name = Column(String, index=True)
    annual_income = Column(Float)
    requested_amount = Column(Float)
    status = Column(String, default="PENDING")
    
    # --- NEW COLUMNS ---
    risk_score = Column(Integer, nullable=True)
    risk_reasoning = Column(String, nullable=True)
```

2. **Update `app/schemas.py`:** Update the `LoanApplicationResponse` schema so the API returns the new fields.
```python
# app/schemas.py
# (Keep previous imports and schemas)

class LoanApplicationResponse(LoanApplicationBase):
    id: int
    status: str
    risk_score: Optional[int] = None
    risk_reasoning: Optional[str] = None

    class Config:
        from_attributes = True
```

3. **Run Alembic Migrations:**
Run the following commands in the terminal to apply the schema changes to the PostgreSQL database:
```bash
alembic revision --autogenerate -m "add risk scoring columns"
alembic upgrade head
```
*(Agent Check: Verify the database table now has `risk_score` and `risk_reasoning` columns before proceeding.)*

## Step 2: Dependencies and Configuration

We need the OpenAI SDK to interact with the LLM.

1. **Update `requirements.txt`:** Add `openai` to the list.
```text
openai
```
Install it via terminal: `pip install openai`

2. **Update `.env`:** Add a placeholder (or real) OpenAI API key.
```text
OPENAI_API_KEY=your_openai_api_key_here
```

3. **Update `app/config.py`:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    openai_api_key: str = "placeholder" # Added for OpenAI

    class Config:
        env_file = ".env"

settings = Settings()
```

## Step 3: Create the Risk Evaluation Service

Create a new file `app/services.py`. This file will contain the business logic: calculating the Debt-to-Income (DTI) ratio and calling OpenAI for a decision.

```python
# app/services.py
import asyncio
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import LoanApplication
from app.config import settings
from pydantic import BaseModel

# Initialize Async OpenAI Client
client = AsyncOpenAI(api_key=settings.openai_api_key)

# Pydantic model for structured AI output
class RiskAssessment(BaseModel):
    risk_score: int
    reasoning: str
    decision_status: str # Should be APPROVED, REJECTED, or UNDER_REVIEW

async def evaluate_loan_risk(loan_id: int, db: AsyncSession):
    # 1. Fetch the loan record
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        return
    
    # 2. Heuristic: Calculate Debt-to-Income Ratio
    dti_ratio = loan.requested_amount / loan.annual_income
    
    # 3. Fast-fail heuristic rule
    if dti_ratio > 0.60:
        loan.status = "REJECTED"
        loan.risk_score = 99
        loan.risk_reasoning = "Automated rejection: DTI ratio exceeds 60% threshold."
        await db.commit()
        return

    # 4. AI Evaluation (using structured outputs)
    prompt = f"""
    Evaluate the following loan application:
    Applicant: {loan.applicant_name}
    Annual Income: ${loan.annual_income}
    Requested Amount: ${loan.requested_amount}
    Calculated DTI Ratio: {dti_ratio:.2f}

    Provide a risk score from 1-100 (1 is lowest risk). 
    If DTI > 0.40, set decision_status to UNDER_REVIEW. 
    Otherwise, set decision_status to APPROVED. 
    Provide a 1-sentence reasoning.
    """
    
    try:
        completion = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert financial underwriter."},
                {"role": "user", "content": prompt}
            ],
            response_format=RiskAssessment,
        )
        
        assessment = completion.choices[0].message.parsed
        
        # 5. Update Database Record
        loan.risk_score = assessment.risk_score
        loan.risk_reasoning = assessment.reasoning
        loan.status = assessment.decision_status
        await db.commit()
        
    except Exception as e:
        print(f"AI Evaluation failed for loan {loan_id}: {e}")
        loan.status = "UNDER_REVIEW"
        loan.risk_reasoning = "System error during AI evaluation. Manual review required."
        await db.commit()
```

## Step 4: Integrate FastAPI Background Tasks

Update `app/main.py` to trigger the `evaluate_loan_risk` service in the background right after a loan is created.

```python
# app/main.py (Modifications only)
from fastapi import BackgroundTasks # NEW IMPORT
from app.services import evaluate_loan_risk # NEW IMPORT

# ... (Keep existing imports and setup) ...

@app.post("/applications/", response_model=LoanApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application: LoanApplicationCreate, 
    background_tasks: BackgroundTasks, # NEW PARAMETER
    db: AsyncSession = Depends(get_async_db)
):
    db_loan = LoanApplication(**application.model_dump())
    db.add(db_loan)
    await db.commit()
    await db.refresh(db_loan)
    
    # NEW: Dispatch the AI evaluation to run in the background
    background_tasks.add_task(evaluate_loan_risk, db_loan.id, db)
    
    # Returns immediately as "PENDING" while the background task runs
    return db_loan

# ... (Keep the rest of the endpoints) ...
```

## Step 5: Verification Phase
**Agent Instructions:**
1. Start the server: `uvicorn app.main:app --reload`
2. Make a `POST` request to `/applications/`. It should return immediately with status `PENDING`.
3. Wait ~3-5 seconds for the background task to complete.
4. Make a `GET` request to `/applications/{id}` to verify that the `status`, `risk_score`, and `risk_reasoning` fields have been populated by the AI.