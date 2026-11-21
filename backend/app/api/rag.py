import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func

from app.api.deps import get_current_user, require_role
from app.db.session import SessionLocal
from app.models.models import ChatMessage, User
from app.services import ingestion
from app.services import rag_qa
from app.services.file_validation import validate_file_signature

KB_STORAGE_DIR = Path(__file__).resolve().parents[1] / "static" / "knowledge_base"
KB_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/rag", tags=["RAG"])

# Knowledge-base chats live in the shared chat_messages table under a
# "kb:" conversation-id prefix so they never mix with AI Chatbot history.
KB_PREFIX = "kb:"
KB_HISTORY_WINDOW = 12  # bounded recent-message window sent to the LLM


def _kb_conversation_id(raw: Optional[str]) -> str:
    """Validate/normalize a client-supplied KB conversation id."""
    if raw and raw.startswith(KB_PREFIX) and len(raw) <= 48:
        return raw
    return f"{KB_PREFIX}{uuid.uuid4()}"


def _kb_owned_conversation(db, conversation_id: str, user_id: int) -> bool:
    return db.query(ChatMessage.id).filter_by(
        conversation_id=conversation_id, user_id=user_id
    ).first() is not None


def _kb_title_from_metadata(metadata: Optional[str]) -> Optional[str]:
    if not metadata:
        return None
    try:
        return json.loads(metadata).get("title")
    except Exception:
        return None


def _kb_set_title(db, conversation_id: str, user_id: int, title: str):
    """Store a custom title on the first user message's metadata."""
    first = db.query(ChatMessage).filter_by(
        conversation_id=conversation_id, user_id=user_id, role="user"
    ).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).first()
    if not first:
        return
    meta = {}
    if first.metadata_json:
        try:
            meta = json.loads(first.metadata_json)
        except Exception:
            meta = {}
    meta["title"] = title[:120]
    first.metadata_json = json.dumps(meta, ensure_ascii=False)
    db.commit()


# ── Task 2: Document Ingestion ────────────────────────────────────────────

@router.post("/ingest", response_model=Dict[str, Any])
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject: Optional[str] = Form("General"),
    grade_level: Optional[str] = Form("All"),
    topic: str = Form("General"),
    is_async: bool = Form(False),
    current_user: User = Depends(require_role("instructor"))
):
    """
    Ingest a PDF or text document into the RAG vector store.
    - Multipart file upload + form fields (subject, grade_level, topic).
    - Validates file content signature (magic bytes) to guard against spoofed extensions.
    - Streams files directly to persistent disk storage to support 100MB+ documents with low memory.
    - Runs in background for large files (>1MB) or if is_async=true, reporting progress via job_id.
    """
    filename = file.filename or "uploaded_document.pdf"
    safe_filename = Path(filename).name.replace("..", "").replace("/", "").replace("\\", "")
    dest_path = KB_STORAGE_DIR / safe_filename

    # Read first chunk (up to 4KB) for signature validation before saving
    first_chunk = await file.read(4096)
    if not first_chunk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    # Magic byte validation
    is_valid_sig, sig_reason = validate_file_signature(filename, first_chunk)
    if not is_valid_sig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File validation failed: {sig_reason}"
        )

    # Stream file to disk in 1MB chunks to maintain constant low memory usage even for 100MB+ PDFs
    file_size = len(first_chunk)
    with open(dest_path, "wb") as f:
        f.write(first_chunk)
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            file_size += len(chunk)

    # Trigger background ingestion if file > 1MB or is_async requested
    if file_size > 1 * 1024 * 1024 or is_async:
        job_id = f"kb-{uuid.uuid4()}"
        ingestion.create_ingestion_job(job_id, filename=filename, total_size=file_size)
        background_tasks.add_task(
            ingestion.process_and_ingest_document,
            filename=filename,
            subject=subject,
            grade_level=grade_level,
            topic=topic,
            source_id=filename,
            file_path=str(dest_path),
            job_id=job_id,
        )
        return {
            "status": "queued",
            "job_id": job_id,
            "message": f"Document '{filename}' queued for background ingestion ({round(file_size / (1024*1024), 1)} MB).",
            "source_id": filename,
            "filename": filename,
            "file_url": f"/static/knowledge_base/{safe_filename}",
            "subject": subject,
            "grade_level": grade_level,
            "topic": topic,
            "file_size": file_size,
        }

    # Synchronous processing for smaller documents
    try:
        result = ingestion.process_and_ingest_document(
            filename=filename,
            subject=subject,
            grade_level=grade_level,
            topic=topic,
            source_id=filename,
            file_path=str(dest_path),
        )
        result["file_url"] = f"/static/knowledge_base/{safe_filename}"
        result["file_size"] = file_size
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and ingest document '{filename}': {str(exc)}"
        )


@router.get("/ingest/status/{job_id}")
def get_ingestion_status(
    job_id: str,
    current_user: User = Depends(require_role("instructor"))
):
    """
    Poll live progress and status of a background document ingestion job.
    """
    job = ingestion.get_ingestion_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.get("/sources/{source_id:path}/file")
def get_source_file(
    source_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Preview or download an already-uploaded Knowledge Base file.
    """
    clean_name = Path(source_id).name
    candidates = [
        KB_STORAGE_DIR / clean_name,
        KB_STORAGE_DIR / f"{clean_name}.pdf",
    ]
    file_path = next((p for p in candidates if p.exists() and p.is_file()), None)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"File for source '{source_id}' was not found on disk.")

    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "text/plain"
    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=file_path.name,
        content_disposition_type="inline",
    )


@router.get("/sources/{source_id:path}/preview")
def preview_source_material(
    source_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Returns document preview information including download/inline URL and sample extracted chunks.
    """
    clean_name = Path(source_id).name
    candidates = [
        KB_STORAGE_DIR / clean_name,
        KB_STORAGE_DIR / f"{clean_name}.pdf",
    ]
    file_path = next((p for p in candidates if p.exists() and p.is_file()), None)
    file_url = f"/static/knowledge_base/{file_path.name}" if file_path else None
    
    # Retrieve top sample chunks from vector store
    sample_chunks = rag_qa.suggest_chunks(topic="", subject=None, grade_level=None, top_k=6, min_score=None).get("chunks", [])
    filtered_chunks = [c for c in sample_chunks if c.get("source_file") == source_id or c.get("filename") == clean_name]
    if not filtered_chunks and sample_chunks:
        filtered_chunks = sample_chunks[:3]

    return {
        "source_id": source_id,
        "filename": clean_name,
        "has_file": file_path is not None,
        "file_url": file_url,
        "file_size": file_path.stat().st_size if file_path else 0,
        "sample_chunks": filtered_chunks,
    }


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
    source_file = payload.get("source_file") or payload.get("source_id") or None
    raw_source_ids = payload.get("source_ids")
    source_ids = [str(s) for s in raw_source_ids] if isinstance(raw_source_ids, list) and raw_source_ids else None
    if source_ids:
        # Validate every selected ID against the indexed sources — the KB is
        # shared, so "ownership" means "must be a real indexed document".
        known = {str(s.get("source_id") or s.get("source_file"))
                 for s in ingestion.get_indexed_sources()}
        unknown = [s for s in source_ids if s not in known]
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f"Unknown source_ids: {', '.join(unknown[:5])}")

    # ── Persistent KB conversation (instructor-scoped) ──────────────────
    conversation_id = payload.get("conversation_id") or None
    persist = bool(payload.get("persist", True))
    db = SessionLocal()
    history: list[dict] = []
    try:
        if conversation_id:
            if not conversation_id.startswith(KB_PREFIX):
                raise HTTPException(status_code=400, detail="Invalid conversation_id")
            if not _kb_owned_conversation(db, conversation_id, current_user.id):
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conversation_id = f"{KB_PREFIX}{uuid.uuid4()}"

        # Bounded recent-message window for multi-turn context
        prior = (
            db.query(ChatMessage)
            .filter_by(conversation_id=conversation_id, user_id=current_user.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(KB_HISTORY_WINDOW)
            .all()
        )
        history = []
        for m in reversed(prior):
            entry = {"role": m.role, "content": m.content}
            # Carry forward the sources the assistant grounded its last answer
            # in, so follow-up questions stay scoped to the same document(s).
            if m.role == "assistant" and getattr(m, "metadata_json", None):
                try:
                    meta = json.loads(m.metadata_json)
                    srcs = meta.get("sources") or []
                    files = [s.get("source_file") for s in srcs
                             if isinstance(s, dict) and s.get("source_file")]
                    if files:
                        entry["sources"] = files
                except Exception:
                    pass
            history.append(entry)

        if persist:
            db.add(ChatMessage(
                conversation_id=conversation_id,
                user_id=current_user.id,
                role="user",
                content=question,
            ))
            db.commit()
    finally:
        db.close()

    result = rag_qa.answer_question(
        question=question,
        subject=subject,
        grade_level=grade_level,
        top_k=top_k,
        source_file=source_file,
        history=history,
        source_ids=source_ids,
    )

    if persist:
        db = SessionLocal()
        try:
            db.add(ChatMessage(
                conversation_id=conversation_id,
                user_id=current_user.id,
                role="assistant",
                content=result.get("answer", ""),
                metadata_json=json.dumps({
                    "sources": result.get("sources", []),
                    "chunks_used": result.get("chunks_used", 0),
                }, ensure_ascii=False),
            ))
            db.commit()
        finally:
            db.close()

    result["conversation_id"] = conversation_id
    return result


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


# ── KB Chat History (instructor-scoped, user-owned) ────────────────────────

class KBRenameIn(BaseModel):
    title: str


@router.get("/chat/conversations")
def kb_list_conversations(
    q: Optional[str] = Query(None, description="Search conversation titles/previews"),
    current_user: User = Depends(require_role("instructor")),
):
    """List the current instructor's KB conversations, newest first."""
    db = SessionLocal()
    try:
        conv_ids = [
            row[0] for row in db.query(ChatMessage.conversation_id)
            .filter(ChatMessage.user_id == current_user.id,
                    ChatMessage.conversation_id.like(f"{KB_PREFIX}%"))
            .group_by(ChatMessage.conversation_id).all()
        ]
        results = []
        for cid in conv_ids:
            msgs = db.query(ChatMessage).filter_by(
                conversation_id=cid, user_id=current_user.id
            ).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()
            if not msgs:
                continue
            first_user = next((m for m in msgs if m.role == "user"), msgs[0])
            custom_title = _kb_title_from_metadata(first_user.metadata_json)
            auto_title = (first_user.content or "").strip().split("\n")[0][:80]
            title = custom_title or auto_title or "Untitled chat"
            if q and q.lower() not in title.lower():
                # also match against any message content
                hit = db.query(ChatMessage.id).filter(
                    ChatMessage.conversation_id == cid,
                    ChatMessage.user_id == current_user.id,
                    ChatMessage.content.ilike(f"%{q}%"),
                ).first()
                if not hit:
                    continue
            results.append({
                "conversation_id": cid,
                "title": title,
                "is_renamed": bool(custom_title),
                "last_at": str(msgs[-1].created_at),
                "message_count": len(msgs),
            })
        results.sort(key=lambda r: r["last_at"], reverse=True)
        return results
    finally:
        db.close()


@router.get("/chat/conversations/{conversation_id}")
def kb_get_conversation(
    conversation_id: str,
    current_user: User = Depends(require_role("instructor")),
):
    """Load full message history for one of the instructor's KB chats."""
    if not conversation_id.startswith(KB_PREFIX):
        raise HTTPException(status_code=404, detail="Conversation not found")
    db = SessionLocal()
    try:
        msgs = db.query(ChatMessage).filter_by(
            conversation_id=conversation_id, user_id=current_user.id
        ).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()
        if not msgs:
            raise HTTPException(status_code=404, detail="Conversation not found")
        out = []
        for m in msgs:
            meta = None
            if m.metadata_json:
                try:
                    meta = json.loads(m.metadata_json)
                except Exception:
                    meta = None
            out.append({
                "role": m.role,
                "content": m.content,
                "created_at": str(m.created_at),
                "metadata": meta,
            })
        return {"conversation_id": conversation_id, "messages": out}
    finally:
        db.close()


@router.patch("/chat/conversations/{conversation_id}")
def kb_rename_conversation(
    conversation_id: str,
    payload: KBRenameIn,
    current_user: User = Depends(require_role("instructor")),
):
    """Rename a KB conversation (title stored on the first user message)."""
    if not conversation_id.startswith(KB_PREFIX):
        raise HTTPException(status_code=404, detail="Conversation not found")
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title must not be empty")
    db = SessionLocal()
    try:
        if not _kb_owned_conversation(db, conversation_id, current_user.id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        _kb_set_title(db, conversation_id, current_user.id, title)
        return {"conversation_id": conversation_id, "title": title[:120]}
    finally:
        db.close()


@router.delete("/chat/conversations/{conversation_id}")
def kb_delete_conversation(
    conversation_id: str,
    current_user: User = Depends(require_role("instructor")),
):
    """Delete one of the instructor's KB conversations."""
    if not conversation_id.startswith(KB_PREFIX):
        raise HTTPException(status_code=404, detail="Conversation not found")
    db = SessionLocal()
    try:
        deleted = db.query(ChatMessage).filter_by(
            conversation_id=conversation_id, user_id=current_user.id
        ).delete()
        db.commit()
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": deleted, "conversation_id": conversation_id}
    finally:
        db.close()
