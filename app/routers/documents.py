"""
app/routers/documents.py — KYC and financial document attachment router.
Stores files locally in zero-cost storage and tracks audit metadata.
"""
import logging
import os
import re
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_async_db
from app.models import LoanApplication, LoanDocument, AuditLog, User
from app.schemas import LoanDocumentResponse
from app.auth.utils import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents & KYC"])

UPLOAD_DIR = Path("uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB limit

# Explicit allow-list: extension → expected MIME type prefix
ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".txt": "text/",
    ".csv": "text/",
}

# Sanitise filename to only alphanumeric, dashes, underscores, and dots
_SAFE_FILENAME_RE = re.compile(r"[^\w.\-]")


@router.post("/applications/{loan_id}/documents", response_model=LoanDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_loan_document(
    loan_id: int,
    document_type: str = Form(..., description="ID_PROOF, INCOME_PROOF, BANK_STATEMENT, COLLATERAL, or OTHER"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a KYC or financial proof document (PDF, PNG, JPG, WEBP) for a loan application.
    Stores the file locally and records metadata in database with audit logs.
    """
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    # Validate file extension against allow-list
    original_filename = file.filename or "unnamed_document"
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    # Validate MIME type (defence-in-depth: don't trust client-side extension alone)
    content_type = file.content_type or ""
    expected_mime_prefix = ALLOWED_TYPES[ext]
    if content_type and not content_type.lower().startswith(expected_mime_prefix):
        raise HTTPException(
            status_code=400,
            detail=f"MIME type '{content_type}' does not match expected type for '{ext}'.",
        )

    # Sanitise filename to prevent path traversal and special char injection
    safe_basename = _SAFE_FILENAME_RE.sub("_", os.path.basename(original_filename))
    safe_name = f"{uuid.uuid4().hex[:12]}_{safe_basename}"

    # Resolve final path and verify it stays within UPLOAD_DIR (path traversal guard)
    loan_upload_dir = UPLOAD_DIR / str(loan_id)
    loan_upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = (loan_upload_dir / safe_name).resolve()
    if not str(target_path).startswith(str(UPLOAD_DIR)):
        logger.error("Path traversal attempt detected: %s", target_path)
        raise HTTPException(status_code=400, detail="Invalid file path.")

    # Write file content to disk in 1 MB chunks
    file_size = 0
    with target_path.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="File size exceeds maximum 15 MB limit")
            buffer.write(chunk)

    logger.info("Document uploaded: loan_id=%d file=%s size=%d bytes", loan_id, safe_name, file_size)

    # Save DB record
    doc = LoanDocument(
        loan_id=loan_id,
        uploaded_by_id=current_user.id,
        document_type=document_type.upper(),
        file_name=original_filename,
        file_path=str(target_path),
        file_size_bytes=file_size,
        content_type=file.content_type,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Audit log
    db.add(AuditLog(
        loan_id=loan_id,
        actor_id=current_user.id,
        action="DOCUMENT_ATTACHED",
        notes=f"Attached {doc.document_type} ({doc.file_name}, {file_size / 1024:.1f} KB)",
    ))
    await db.commit()

    return doc


@router.get("/applications/{loan_id}/documents", response_model=List[LoanDocumentResponse])
async def list_loan_documents(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List all documents attached to a loan application."""
    loan = await db.get(LoanApplication, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan application not found")

    result = await db.execute(
        select(LoanDocument)
        .where(LoanDocument.loan_id == loan_id)
        .order_by(LoanDocument.uploaded_at.desc())
    )
    return result.scalars().all()


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Download or view an attached document by ID."""
    doc = await db.get(LoanDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing from storage")

    return FileResponse(
        path=str(file_path),
        filename=doc.file_name,
        media_type=doc.content_type or "application/octet-stream",
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an attached document from database and local storage."""
    doc = await db.get(LoanDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink(missing_ok=True)

    loan_id = doc.loan_id
    doc_name = doc.file_name

    await db.delete(doc)

    db.add(AuditLog(
        loan_id=loan_id,
        actor_id=current_user.id,
        action="DOCUMENT_DELETED",
        notes=f"Removed document: {doc_name}",
    ))
    await db.commit()
    return None
