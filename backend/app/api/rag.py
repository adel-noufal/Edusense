from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import get_current_user, require_role
from app.models.models import User
from app.services import ingestion

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/ingest", response_model=Dict[str, Any])
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject: str = Form(...),
    grade_level: str = Form(...),
    topic: str = Form(...),
    is_async: bool = Form(False),
    current_user: User = Depends(require_role("instructor"))
):
    """
    Ingest a PDF or text document into the RAG vector store.
    - Multipart file upload + form fields (subject, grade_level, topic).
    - Restricted to 'instructor' role (and admins).
    - Runs in background for large files (>1MB) or if requested.
    """
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    filename = file.filename or "uploaded_document.pdf"

    # For large files (>1MB) or async flag, process as background task
    if len(content) > 1 * 1024 * 1024 or is_async:
        background_tasks.add_task(
            ingestion.process_and_ingest_document,
            file_bytes=content,
            filename=filename,
            subject=subject,
            grade_level=grade_level,
            topic=topic,
            source_id=filename
        )
        return {
            "status": "queued",
            "message": f"Document '{filename}' ingestion started in background.",
            "source_id": filename,
            "filename": filename,
            "subject": subject,
            "grade_level": grade_level,
            "topic": topic,
        }

    # Synchronous processing for normal files
    result = ingestion.process_and_ingest_document(
        file_bytes=content,
        filename=filename,
        subject=subject,
        grade_level=grade_level,
        topic=topic,
        source_id=filename
    )
    return result


@router.get("/sources", response_model=List[Dict[str, Any]])
def get_sources(
    current_user: User = Depends(get_current_user)
):
    """
    List all indexed document sources in the RAG vector store with chunk counts, tags, and ingestion dates.
    """
    return ingestion.get_indexed_sources()


@router.delete("/sources/{source_id:path}", response_model=Dict[str, Any])
def delete_source(
    source_id: str,
    current_user: User = Depends(require_role("instructor"))
):
    """
    Delete a document source and all its associated vector chunks by source_id.
    Restricted to 'instructor' role (and admins).
    """
    ingestion.delete_source_chunks(source_id)
    return {
        "status": "success",
        "message": f"Document source '{source_id}' and all chunks successfully removed.",
        "source_id": source_id
    }
