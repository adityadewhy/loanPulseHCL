"""
app/services/risk_engine.py

AI Risk Underwriting Engine
Priority Chain: Gemini (free) → Groq (free) → Deterministic DTI fallback
Never crashes. Never requires a paid API.
"""
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import LoanApplication
from app.config import settings

logger = logging.getLogger(__name__)


# ── Deterministic Rules (always available, no API needed) ──────────────────

def calculate_dti(requested_amount: float, annual_income: float) -> float:
    return requested_amount / annual_income


def deterministic_assessment(loan: LoanApplication) -> dict:
    """
    Pure math, zero external calls.
    Returns a risk assessment dict based on DTI and income bands.
    """
    dti = calculate_dti(loan.requested_amount, loan.annual_income)

    if dti > 0.60:
        return {
            "risk_score": 95,
            "reasoning": f"Auto-rejected: DTI ratio of {dti:.1%} exceeds the 60% policy threshold.",
            "decision_status": "REJECTED",
        }
    elif dti > 0.40:
        score = int(50 + (dti - 0.40) / 0.20 * 40)  # scales 50–90
        return {
            "risk_score": score,
            "reasoning": f"DTI of {dti:.1%} is in the elevated range (40–60%). Requires officer review.",
            "decision_status": "UNDER_REVIEW",
        }
    else:
        score = int(dti / 0.40 * 40 + 5)  # scales 5–45
        return {
            "risk_score": score,
            "reasoning": f"DTI of {dti:.1%} is within acceptable limits. Application is financially sound.",
            "decision_status": "APPROVED",
        }


# ── Gemini Provider (google-genai SDK, free tier) ──────────────────────────

async def _gemini_evaluate(loan: LoanApplication) -> dict:
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    from google import genai
    client = genai.Client(api_key=settings.gemini_api_key)

    dti = calculate_dti(loan.requested_amount, loan.annual_income)
    prompt = f"""You are a financial underwriter. Evaluate this loan application and respond ONLY with valid JSON.

Application:
- Applicant: {loan.applicant_name}
- Annual Income: ${loan.annual_income:,.0f}
- Requested Amount: ${loan.requested_amount:,.0f}
- DTI Ratio: {dti:.2f}

Respond with this exact JSON structure:
{{
  "risk_score": <integer 1-100, where 1 is lowest risk>,
  "reasoning": "<one clear sentence explaining the decision>",
  "decision_status": "<one of: APPROVED, REJECTED, UNDER_REVIEW>"
}}

Rules:
- DTI > 0.60 → REJECTED
- DTI 0.40–0.60 → UNDER_REVIEW
- DTI < 0.40 → APPROVED"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    text = response.text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    return json.loads(text)


# ── Groq Provider (free tier) ──────────────────────────────────────────────

async def _groq_evaluate(loan: LoanApplication) -> dict:
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY not configured")

    from groq import AsyncGroq
    client = AsyncGroq(api_key=settings.groq_api_key)

    dti = calculate_dti(loan.requested_amount, loan.annual_income)
    completion = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": "You are a financial underwriter. Always respond with valid JSON only.",
            },
            {
                "role": "user",
                "content": f"""Evaluate this loan application:
- Applicant: {loan.applicant_name}
- Annual Income: ${loan.annual_income:,.0f}
- Requested Amount: ${loan.requested_amount:,.0f}
- DTI Ratio: {dti:.2f}

Respond with JSON: {{"risk_score": int, "reasoning": "str", "decision_status": "APPROVED|REJECTED|UNDER_REVIEW"}}
Rules: DTI>0.60=REJECTED, DTI 0.40-0.60=UNDER_REVIEW, DTI<0.40=APPROVED""",
            },
        ],
        response_format={"type": "json_object"},
    )

    return json.loads(completion.choices[0].message.content)


# ── Main Entry Point ───────────────────────────────────────────────────────

async def evaluate_loan_risk(loan_id: int, db: AsyncSession):
    """
    Evaluate loan risk and update the DB record.
    Provider priority: Gemini → Groq → Deterministic fallback.
    This function NEVER raises — it always commits a result.
    """
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        logger.warning("evaluate_loan_risk: loan_id=%d not found", loan_id)
        return

    assessment = None

    # Tier 1: Fast-fail deterministic check for clear rejections
    dti = calculate_dti(loan.requested_amount, loan.annual_income)
    if dti > 0.60:
        assessment = deterministic_assessment(loan)
        _apply_assessment(loan, assessment)
        await db.commit()
        return

    # Tier 2: Gemini (free)
    try:
        assessment = await _gemini_evaluate(loan)
        logger.info("RiskEngine: Gemini evaluated loan_id=%d score=%s", loan_id, assessment.get("risk_score"))
    except Exception as exc:
        logger.warning("RiskEngine: Gemini failed for loan_id=%d: %s", loan_id, exc)

    # Tier 3: Groq (free)
    if assessment is None:
        try:
            assessment = await _groq_evaluate(loan)
            logger.info("RiskEngine: Groq evaluated loan_id=%d score=%s", loan_id, assessment.get("risk_score"))
        except Exception as exc:
            logger.warning("RiskEngine: Groq failed for loan_id=%d: %s", loan_id, exc)

    # Tier 4: Deterministic fallback (always works)
    if assessment is None:
        assessment = deterministic_assessment(loan)
        assessment["reasoning"] = "[Deterministic] " + assessment["reasoning"]
        logger.info("RiskEngine: Using deterministic fallback for loan_id=%d", loan_id)

    _apply_assessment(loan, assessment)
    await db.commit()


def _apply_assessment(loan: LoanApplication, assessment: dict):
    loan.risk_score = int(assessment.get("risk_score", 50))
    loan.risk_reasoning = assessment.get("reasoning", "")
    loan.status = assessment.get("decision_status", "UNDER_REVIEW")
