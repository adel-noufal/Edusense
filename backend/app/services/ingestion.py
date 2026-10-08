import os
import uuid
import datetime
import io
from typing import List, Dict, Any, Optional
from pypdf import PdfReader
import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.vector_store import (
    ChunkMetadata,
    ChunkRecord,
    add_chunks,
    delete_by_source,
    init_collection
)

# Initialize tiktoken encoder for cl100k_base (OpenAI/standard RAG tokenizer)
try:
    _tokenizer = tiktoken.get_encoding("cl100k_base")
except Exception:
    _tokenizer = None


def _count_tokens(text: str) -> int:
    """Accurately counts tokens in text string using tiktoken."""
    if _tokenizer:
        return len(_tokenizer.encode(text))
    # Fallback to word approximation if tiktoken is unavailable
    return len(text.split())


# RecursiveCharacterTextSplitter targeting 500-1000 tokens with 100 token overlap
_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=750,
    chunk_overlap=100,
    length_function=_count_tokens,
    separators=["\n\n", "\n", ". ", " ", ""]
)


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
