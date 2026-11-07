import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.services.source_extractor import extract_text_from_file
from app.services.vector_store import (
    ChunkMetadata,
    ChunkRecord,
    add_chunks,
    delete_by_source,
)


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
