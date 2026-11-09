import os
import uuid
import datetime
import io
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pypdf import PdfReader
import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

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

def extract_pdf_pages(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from raw PDF binary bytes.
    Returns a list of dicts: [{"page": page_num, "text": page_text}].
    Preserves 1-indexed page numbers.
    """
    pdf_file = io.BytesIO(file_content)
    reader = PdfReader(pdf_file)
    pages_content = []

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            pages_content.append({"page": page_num, "text": page_text})

    return pages_content


def process_and_ingest_document(
    file_bytes: bytes,
    filename: str,
    subject: str,
    grade_level: str,
    topic: str,
    source_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingests a document (PDF or plain text) into ChromaDB vector store.
    - Extracts text preserving page numbers in metadata.
    - Chunks text into 500-1000 token pieces with 100 token overlap.
    - Attaches subject, grade_level, topic, source_file, page, and ingestion_date.
    - Embeds and stores chunks via vector_store.add_chunks().
    """
    if not source_id:
        source_id = filename

    # Purge any previous chunks for this source to ensure idempotency
    delete_by_source(source_id)

    ingestion_date = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pages_content: List[Dict[str, Any]] = []

    if filename.lower().endswith(".pdf"):
        pages_content = extract_pdf_pages(file_bytes)
    else:
        # For non-PDF text documents (e.g. .txt, .md)
        text = file_bytes.decode("utf-8", errors="ignore").strip()
        if text:
            pages_content = [{"page": 1, "text": text}]

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

    if chunk_records:
        add_chunks(chunk_records)

    return {
        "source_id": source_id,
        "filename": filename,
        "chunk_count": len(chunk_records),
        "subject": subject,
        "grade_level": grade_level,
        "topic": topic,
        "ingestion_date": ingestion_date,
        "status": "success"
    }


def get_indexed_sources() -> List[Dict[str, Any]]:
    """
    Lists all indexed documents from ChromaDB vector store with chunk counts,
    subject/grade tags, topic, and ingestion date.
    """
    collection = init_collection()
    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", []) or []

    sources_map: Dict[str, Dict[str, Any]] = {}
    for meta in metadatas:
        if not meta:
            continue
        source_id = str(meta.get("source_id") or meta.get("source_file") or "unknown")
        if source_id not in sources_map:
            sources_map[source_id] = {
                "source_id": source_id,
                "filename": str(meta.get("filename") or meta.get("source_file") or source_id),
                "subject": str(meta.get("subject", "")),
                "grade_level": str(meta.get("grade_level", "")),
                "topic": str(meta.get("topic", "")),
                "ingestion_date": str(meta.get("ingestion_date", "")),
                "chunk_count": 0
            }
        sources_map[source_id]["chunk_count"] += 1

    return list(sources_map.values())


def delete_source_chunks(source_id: str) -> bool:
    """
    Removes all chunks associated with a document source from the vector store.
    """
    delete_by_source(source_id)
    return True