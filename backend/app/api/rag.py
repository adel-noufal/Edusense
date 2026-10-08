from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import get_current_user, require_role
from app.models.models import User
from app.services import ingestion
from app.services import rag_qa

router = APIRouter(prefix="/rag", tags=["RAG"])


# ── Task 2: Document Ingestion ────────────────────────────────────────────

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
    - Runs in background for large files (>1MB) or if is_async=true.
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
    List all indexed document sources in the RAG vector store with chunk counts,
    tags, and ingestion dates. Accessible to all authenticated users.
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


# ── Task 5: Student RAG Q&A ───────────────────────────────────────────────

@router.post("/ask", response_model=Dict[str, Any])
def ask_question(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    **Student Q&A** — Ask a question and receive an AI answer grounded in the
    indexed course material (RAG).

    Request body:
    ```json
    {
      "question": "What is photosynthesis?",
      "subject":      "Biology",      // optional filter
      "grade_level":  "10",           // optional filter
      "top_k":        5               // optional, default 5
    }
    ```

    Response:
    ```json
    {
      "question":    "...",
      "answer":      "...",
      "sources":     [{"source_file", "page", "subject", "grade_level", "topic", "score"}],
      "chunks_used": 2,
      "subject":     "Biology",
      "grade_level": "10"
    }
    ```
    - Open to **all authenticated users** (students and instructors).
    - If no relevant material exists, returns a polite message asking the instructor to upload documents.
    - AI answer uses Gemini → Ollama → fallback message chain.
    """
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="'question' field is required and must not be empty.")

    subject     = payload.get("subject")     or None
    grade_level = payload.get("grade_level") or None
    top_k       = int(payload.get("top_k", 5))

    return rag_qa.answer_question(
        question=question,
        subject=subject,
        grade_level=grade_level,
        top_k=top_k,
    )


# ── Task 6: Instructor Knowledge-Base Suggestions ────────────────────────

@router.get("/suggest", response_model=Dict[str, Any])
def suggest_material(
    topic: str = Query(..., description="Topic or keyword to search the knowledge base for."),
    subject: Optional[str] = Query(None, description="Filter by subject (e.g. Biology)."),
    grade_level: Optional[str] = Query(None, description="Filter by grade level (e.g. 10)."),
    top_k: int = Query(8, ge=1, le=20, description="Number of top chunks to return."),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum similarity score (0–1)."),
    current_user: User = Depends(require_role("instructor"))
):
    """
    **Instructor Knowledge-Base Suggestions** — Preview what source material
    exists in the knowledge base for a given topic before generating content.

    Returns the top-k most relevant chunks ranked by similarity score.
    Use this to verify that a topic has sufficient coverage before running
    `/ai/lessons`, `/ai/quizzes`, or `/ai/flashcards`.

    Query params:
    - `topic` *(required)* — keyword or topic phrase
    - `subject` — optional subject filter
    - `grade_level` — optional grade level filter
    - `top_k` — number of chunks (default 8, max 20)
    - `min_score` — override the default relevance threshold

    Response:
    ```json
    {
      "topic":        "Photosynthesis",
      "subject":      "Biology",
      "grade_level":  "10",
      "total":        2,
      "chunks": [
        {"text": "...", "source_file": "bio_ch4.pdf", "page": 12, "score": 0.87, ...}
      ]
    }
    ```
    """
    return rag_qa.suggest_chunks(
        topic=topic,
        subject=subject,
        grade_level=grade_level,
        top_k=top_k,
        min_score=min_score,
    )
