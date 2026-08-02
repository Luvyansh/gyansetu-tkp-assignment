"""Document upload and metadata routes."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, limiter, verify_api_key
from backend.app.api.pipeline_runner import run_job_pipeline
from backend.app.config import get_settings
from backend.app.db.models import Document, Job
from backend.app.schemas.document import (
    DocTypeHint,
    DocumentDetailResponse,
    DocumentUploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx"}
_MAGIC_PDF = b"%PDF"
_MAGIC_ZIP = b"PK\x03\x04"


def _validate_magic(filename: str, header: bytes) -> None:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        if not header.startswith(_MAGIC_PDF):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content is not a valid PDF (magic bytes mismatch)",
            )
    elif ext in {".docx", ".pptx"}:
        if not header.startswith(_MAGIC_ZIP):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File content is not a valid {ext} (ZIP magic bytes mismatch)",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported extension: {ext}. Allowed: pdf, docx, pptx",
        )


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    summary="Upload an educational document",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, DOCX, or PPTX source file"),
    doc_type_hint: DocTypeHint | None = Form(
        default=None,
        description="Optional document type hint for the parsing router",
    ),
    auto_start: bool = Form(
        default=True,
        description="If true, schedule the pipeline immediately after upload",
    ),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Accept a multipart upload, create Document + Job rows, and optionally start the pipeline.

    Validates extension, size (``settings.max_upload_bytes``), and magic bytes.
    Raw bytes are written to a temp file for the pipeline and are not stored in the DB.
    """
    settings = get_settings()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: .pdf, .docx, .pptx",
        )

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max upload size of {settings.max_upload_bytes} bytes",
        )

    _validate_magic(file.filename, raw[:8])

    suffix = ext
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="tkp_upload_") as tmp:
        tmp.write(raw)
        tmp.flush()
        temp_path = tmp.name

    document = Document(
        original_filename=file.filename,
        doc_type_hint=doc_type_hint.value if doc_type_hint else None,
        extracted_text=None,
        extracted_structure={"temp_file_path": temp_path},
    )
    db.add(document)
    await db.flush()

    job = Job(
        document_id=document.id,
        status="pending",
        current_stage="pending",
        progress_pct=0.0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(document)
    await db.refresh(job)

    if auto_start:
        background_tasks.add_task(run_job_pipeline, job.id)

    return DocumentUploadResponse(
        document_id=document.id,
        job_id=job.id,
        message="Upload accepted; job created" + (" and started" if auto_start else ""),
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document metadata",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def get_document(
    request: Request,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    """Return metadata for an uploaded document (no raw file bytes)."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    structure = document.extracted_structure or {}
    page_count = None
    parser_route = None
    if isinstance(structure, dict):
        page_count = structure.get("page_count")
        parser_route = structure.get("parser_route")

    hint = None
    if document.doc_type_hint:
        try:
            hint = DocTypeHint(document.doc_type_hint)
        except ValueError:
            hint = None

    return DocumentDetailResponse(
        id=document.id,
        original_filename=document.original_filename,
        doc_type_hint=hint,
        created_at=document.created_at,
        page_count=page_count if isinstance(page_count, int) else None,
        parser_route=parser_route if isinstance(parser_route, str) else None,
    )
