import os
import uuid
import datetime
import io
import re
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pypdf import PdfReader
import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

KB_DIR = Path(__file__).resolve().parents[1] / "static" / "knowledge_base"
KB_DIR.mkdir(parents=True, exist_ok=True)

_jobs_lock = threading.Lock()
_ingestion_jobs: Dict[str, Dict[str, Any]] = {}


def create_ingestion_job(job_id: str, filename: str, total_size: int = 0) -> Dict[str, Any]:
    with _jobs_lock:
        job = {
            "job_id": job_id,
            "filename": filename,
            "total_size": total_size,
            "status": "queued",
            "progress": 5,
            "message": "Queued for processing...",
            "chunks_indexed": 0,
            "total_pages": 0,
            "current_page": 0,
            "error": None,
            "file_url": f"/static/knowledge_base/{filename}",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        _ingestion_jobs[job_id] = job
        return job


def update_ingestion_progress(
    job_id: str,
    progress: int,
    message: str,
    chunks_indexed: int = 0,
    total_pages: int = 0,
    current_page: int = 0,
):
    with _jobs_lock:
        if job_id in _ingestion_jobs:
            _ingestion_jobs[job_id]["status"] = "processing"
            _ingestion_jobs[job_id]["progress"] = progress
            _ingestion_jobs[job_id]["message"] = message
            if chunks_indexed:
                _ingestion_jobs[job_id]["chunks_indexed"] = chunks_indexed
            if total_pages:
                _ingestion_jobs[job_id]["total_pages"] = total_pages
            if current_page:
                _ingestion_jobs[job_id]["current_page"] = current_page


def complete_ingestion_job(job_id: str, result: Dict[str, Any]):
    with _jobs_lock:
        if job_id in _ingestion_jobs:
            _ingestion_jobs[job_id]["status"] = "completed"
            _ingestion_jobs[job_id]["progress"] = 100
            _ingestion_jobs[job_id]["message"] = f"Complete: {result.get('chunk_count', 0)} chunks indexed."
            _ingestion_jobs[job_id]["result"] = result
            _ingestion_jobs[job_id]["chunks_indexed"] = result.get("chunk_count", 0)


def fail_ingestion_job(job_id: str, error_message: str):
    with _jobs_lock:
        if job_id in _ingestion_jobs:
            _ingestion_jobs[job_id]["status"] = "failed"
            _ingestion_jobs[job_id]["progress"] = 100
            _ingestion_jobs[job_id]["error"] = error_message
            _ingestion_jobs[job_id]["message"] = f"Failed: {error_message}"


def get_ingestion_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        return _ingestion_jobs.get(job_id)

from app.services.source_extractor import extract_text_from_file
from app.services.vector_store import (
    ChunkMetadata,
    ChunkRecord,
    add_chunks,
    delete_by_source,
    init_collection
)

# Lazy tiktoken encoder for cl100k_base (avoids 50s network timeout on module import)
_tokenizer_cache = "UNINITIALIZED"

def _get_tokenizer():
    global _tokenizer_cache
    if _tokenizer_cache == "UNINITIALIZED":
        try:
            _tokenizer_cache = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tokenizer_cache = None
    return _tokenizer_cache


def _count_tokens(text: str) -> int:
    """Accurately counts tokens in text string using tiktoken."""
    tok = _get_tokenizer()
    if tok:
        return len(tok.encode(text))
    # Fallback to word approximation if tiktoken is unavailable
    return len(text.split())


# RecursiveCharacterTextSplitter targeting 500-1000 tokens with 100 token overlap
_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=750,
    chunk_overlap=100,
    length_function=_count_tokens,
    separators=["\n\n", "\n", ". ", " ", ""]
)


# ─── New Package: Character-based chunking ────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[str]:
    """
    Splits text into overlapping chunks, discarding empty/whitespace-only chunks.
    Ensures robust step progression to prevent zero or negative increments.
    """
    if not text:
        return []

    clean_text = text.strip()
    if not clean_text:
        return []

    if chunk_size <= 0:
        chunk_size = 1000
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))

    if len(clean_text) <= chunk_size:
        return [clean_text]

    step = max(1, chunk_size - chunk_overlap)
    chunks: List[str] = []
    start = 0
    text_len = len(clean_text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start += step

    return chunks


def _build_chunk_metadata(
    base_metadata: Optional[Union[ChunkMetadata, Dict[str, Any]]],
    source_filename: str,
    chunk_index: int,
    total_chunks: int,
) -> ChunkMetadata:
    """
    Merges incoming document metadata with source_file and chunk progression fields,
    returning a structured ChunkMetadata object.
    """
    if isinstance(base_metadata, ChunkMetadata):
        data = base_metadata.model_dump(exclude_none=True)
    elif isinstance(base_metadata, dict):
        data = {k: v for k, v in base_metadata.items() if v is not None}
    else:
        data = {}

    if not data.get("source_file"):
        data["source_file"] = source_filename

    data["chunk_index"] = chunk_index
    data["total_chunks"] = total_chunks

    return ChunkMetadata(**data)


def ingest_file(
    file_path: Union[str, Path],
    metadata: Optional[Union[ChunkMetadata, Dict[str, Any]]] = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    collection_name: Optional[str] = None,
) -> List[ChunkRecord]:
    """
    Ingests a local file into the vector store:
    1. Validates that the file exists on the local filesystem.
    2. Resolves consistent document source identifiers (`source_id` or `source_file`).
    3. Purges any existing chunks for this document using `delete_by_source()`.
    4. Extracts text using `extract_text_from_file`.
    5. Splits text into non-empty overlapping chunks using `chunk_text`.
    6. Converts chunks into `ChunkRecord` and `ChunkMetadata` models.
    7. Stores records in ChromaDB via `add_chunks()`.

    Returns the list of indexed `ChunkRecord` instances.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise FileNotFoundError(f"File not found or is not a regular file: {file_path}")

    # Determine stable source identifier for deletion, IDs, and metadata
    meta_dict = (
        metadata.model_dump(exclude_none=True)
        if isinstance(metadata, ChunkMetadata)
        else (metadata or {})
    )
    source_filename = str(meta_dict.get("source_file") or path.name)
    source_identifier = str(meta_dict.get("source_id") or source_filename)

    # Purge any previous chunks belonging to this document before processing/inserting.
    # Calling this prior to text extraction ensures that if content is cleared or empty,
    # stale chunks are not retained in the vector store.
    delete_by_source(source_identifier, collection_name=collection_name)

    raw_text = extract_text_from_file(str(path))
    if not raw_text or not raw_text.strip():
        return []

    chunks = chunk_text(
        text=raw_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not chunks:
        return []

    total_chunks = len(chunks)
    safe_prefix = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", source_identifier)

    records: List[ChunkRecord] = []
    for idx, chunk_content in enumerate(chunks):
        chunk_id = f"{safe_prefix}_chunk_{idx}"
        chunk_meta = _build_chunk_metadata(
            base_metadata=metadata,
            source_filename=source_filename,
            chunk_index=idx,
            total_chunks=total_chunks,
        )
        records.append(
            ChunkRecord(
                id=chunk_id,
                text=chunk_content,
                metadata=chunk_meta,
            )
        )

    add_chunks(records, collection_name=collection_name)
    return records


# ─── Existing: Token-based ingestion for /api/rag/ingest ──────────────────────

def extract_pdf_pages(
    file_content: Optional[bytes] = None,
    file_path: Optional[str] = None,
    job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from raw PDF bytes or directly from a disk file path.
    Streaming from a disk file path enables 100MB+ PDFs to process with minimal memory.
    """
    if file_path and os.path.exists(file_path):
        reader = PdfReader(file_path)
    elif file_content:
        reader = PdfReader(io.BytesIO(file_content))
    else:
        return []

    pages_content = []
    total_pages = len(reader.pages)

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            pages_content.append({"page": page_num, "text": page_text})

        if job_id and total_pages > 0 and (idx % 10 == 0 or idx == total_pages - 1):
            pct = 10 + int((idx / total_pages) * 60)
            update_ingestion_progress(
                job_id,
                pct,
                f"Extracting text from page {page_num}/{total_pages}...",
                total_pages=total_pages,
                current_page=page_num,
            )

    return pages_content


def process_and_ingest_document(
    file_bytes: Optional[bytes] = None,
    filename: str = "uploaded_document.pdf",
    subject: str = "General",
    grade_level: str = "General",
    topic: str = "General",
    source_id: Optional[str] = None,
    file_path: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingests a document (PDF or plain text) into ChromaDB vector store.
    - Extracts text preserving page numbers in metadata.
    - Chunks text into 500-1000 token pieces with 100 token overlap.
    - Attaches subject, grade_level, topic, source_file, page, and ingestion_date.
    - Embeds and stores chunks via vector_store.add_chunks() in batches.
    - Reports live progress via job_id if provided.
    """
    try:
        if not source_id:
            source_id = filename

        # Purge any previous chunks for this source to ensure idempotency
        delete_by_source(source_id)

        if job_id:
            update_ingestion_progress(job_id, 10, f"Extracting content from '{filename}'...")

        ingestion_date = datetime.datetime.now(datetime.timezone.utc).isoformat()
        pages_content: List[Dict[str, Any]] = []

        if filename.lower().endswith(".pdf"):
            pages_content = extract_pdf_pages(file_content=file_bytes, file_path=file_path, job_id=job_id)
        else:
            # For non-PDF text documents (e.g. .txt, .md)
            if file_path and os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as tf:
                    text = tf.read().strip()
            elif file_bytes:
                text = file_bytes.decode("utf-8", errors="ignore").strip()
            else:
                text = ""
            if text:
                pages_content = [{"page": 1, "text": text}]

        if job_id:
            update_ingestion_progress(job_id, 70, f"Partitioning text into semantic chunks ({len(pages_content)} pages parsed)...")

        chunk_records: List[ChunkRecord] = []
        global_chunk_count = 0

        for item in pages_content:
            page_num = item["page"]
            page_text = item["text"]

            # Chunk text for this page
            raw_chunks = _text_splitter.split_text(page_text)

            for chunk_text in raw_chunks:
                global_chunk_count += 1
                chunk_id = f"{source_id}_p{page_num}_c{global_chunk_count}_{uuid.uuid4().hex[:6]}"

                metadata = ChunkMetadata(
                    subject=subject,
                    grade_level=grade_level,
                    topic=topic,
                    source_file=source_id,
                    source_id=source_id,
                    filename=filename,
                    page=page_num,
                    ingestion_date=ingestion_date,
                )

                chunk_records.append(
                    ChunkRecord(
                        id=chunk_id,
                        text=chunk_text,
                        metadata=metadata
                    )
                )

        if job_id:
            update_ingestion_progress(job_id, 85, f"Generating vector embeddings and indexing {len(chunk_records)} chunks...")

        if chunk_records:
            add_chunks(chunk_records)

        result = {
            "source_id": source_id,
            "filename": filename,
            "chunk_count": len(chunk_records),
            "chunks_added": len(chunk_records),
            "subject": subject,
            "grade_level": grade_level,
            "topic": topic,
            "file_url": f"/static/knowledge_base/{Path(filename).name}",
            "ingestion_date": ingestion_date,
            "status": "success",
        }

        if job_id:
            complete_ingestion_job(job_id, result)

        return result
    except Exception as exc:
        if job_id:
            fail_ingestion_job(job_id, str(exc))
        raise


def get_indexed_sources() -> List[Dict[str, Any]]:
    """
    Lists all indexed documents from ChromaDB vector store with chunk counts,
    subject/grade tags, topic, ingestion date, and physical file preview availability.
    """
    collection = init_collection()
    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", []) or []

    sources_map: Dict[str, Dict[str, Any]] = {}
    for meta in metadatas:
        if not meta:
            continue
        source_id = str(meta.get("source_id") or meta.get("source_file") or "unknown")
        fn = str(meta.get("filename") or meta.get("source_file") or source_id)
        if source_id not in sources_map:
            ing_date = str(meta.get("ingestion_date", ""))
            sources_map[source_id] = {
                "source_id": source_id,
                "source_file": source_id,
                "filename": fn,
                "subject": str(meta.get("subject", "")),
                "grade_level": str(meta.get("grade_level", "")),
                "topic": str(meta.get("topic", "")),
                "ingestion_date": ing_date,
                "ingested_at": ing_date,
                "chunk_count": 0,
                "has_file": False,
                "file_url": None,
                "file_size": 0,
            }
        sources_map[source_id]["chunk_count"] += 1

    # Check physical file availability on disk for each source
    for source_id, item in sources_map.items():
        fn_clean = Path(item["filename"]).name
        sid_clean = Path(source_id).name
        candidates = [
            KB_DIR / fn_clean,
            KB_DIR / sid_clean,
            KB_DIR / f"{sid_clean}.pdf",
        ]
        found = next((p for p in candidates if p.exists() and p.is_file()), None)
        if found:
            item["has_file"] = True
            item["file_url"] = f"/static/knowledge_base/{found.name}"
            item["file_size"] = found.stat().st_size

    return list(sources_map.values())


def delete_source_chunks(source_id: str) -> bool:
    """
    Removes all chunks associated with a document source from the vector store,
    and removes any physical stored file on disk.
    """
    delete_by_source(source_id)
    sid_clean = Path(source_id).name
    for candidate in [KB_DIR / sid_clean, KB_DIR / f"{sid_clean}.pdf"]:
        if candidate.exists() and candidate.is_file():
            try:
                candidate.unlink(missing_ok=True)
            except Exception:
                pass
    return True
