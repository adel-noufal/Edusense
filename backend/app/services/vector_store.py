import os
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import get_settings

DEFAULT_COLLECTION_NAME = "edusense_knowledge"

_client_instance: Optional[chromadb.PersistentClient] = None
_embedding_function = None
_active_collection: Optional[chromadb.Collection] = None


class ChunkMetadata(BaseModel):
    """
    Structured metadata for a chunk record.
    Supports subject, grade_level, topic, source_file, and page,
    while allowing arbitrary additional fields.
    """
    subject: Optional[str] = None
    grade_level: Optional[str] = None
    topic: Optional[str] = None
    source_file: Optional[str] = None
    page: Optional[Union[int, str]] = None

    model_config = {"extra": "allow"}


class ChunkRecord(BaseModel):
    """
    Represents an indexed document chunk for vector storage.
    """
    id: str
    text: str
    metadata: Union[ChunkMetadata, Dict[str, Any]] = Field(default_factory=dict)


def _normalize_metadata(
    meta: Union[ChunkMetadata, Dict[str, Any], None]
) -> Dict[str, Union[str, int, float, bool]]:
    """
    Ensures metadata contains only ChromaDB-compatible primitive types (str, int, float, bool),
    filtering out None values.
    """
    if meta is None:
        return {}
    if isinstance(meta, BaseModel):
        raw = meta.model_dump(exclude_none=True)
    elif isinstance(meta, dict):
        raw = {k: v for k, v in meta.items() if v is not None}
    else:
        raw = {}

    clean: Dict[str, Union[str, int, float, bool]] = {}
    for k, v in raw.items():
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


def get_client(persist_directory: Optional[str] = None) -> chromadb.PersistentClient:
    """
    Returns a persistent ChromaDB client pointing to CHROMA_PERSIST_DIR.
    Runs locally without external services or Docker.
    """
    global _client_instance
    if _client_instance is None or persist_directory is not None:
        settings = get_settings()
        target_dir = persist_directory or settings.chroma_persist_dir
        abs_path = os.path.abspath(target_dir)
        os.makedirs(abs_path, exist_ok=True)
        client = chromadb.PersistentClient(path=abs_path)
        if persist_directory is None:
            _client_instance = client
        return client
    return _client_instance


def get_embedding_function(model_name: Optional[str] = None):
    """
    Returns the local ONNX/SentenceTransformer embedding function for all-MiniLM-L6-v2.
    Tries Chroma's ONNXMiniLM_L6_V2 first (using local cache ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/),
    falling back to SentenceTransformerEmbeddingFunction.
    """
    global _embedding_function
    if _embedding_function is None or model_name is not None:
        try:
            embedding_fn = embedding_functions.ONNXMiniLM_L6_V2()
        except Exception:
            settings = get_settings()
            selected_model = model_name or settings.embedding_model
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=selected_model
            )

        if model_name is None:
            _embedding_function = embedding_fn
        return embedding_fn
    return _embedding_function






def init_collection(name: str = DEFAULT_COLLECTION_NAME) -> chromadb.Collection:
    """
    Initializes and returns a persistent ChromaDB collection with cosine distance.
    Sets the initialized collection as the active default collection.
    """
    global _active_collection
    client = get_client()
    embedding_fn = get_embedding_function()
    collection = client.get_or_create_collection(
        name=name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"}
    )
    _active_collection = collection
    return collection


def add_chunks(
    chunks: List[ChunkRecord],
    collection_name: Optional[str] = None
) -> None:
    """
    Adds or upserts a list of ChunkRecords into the persistent vector collection.
    """
    if not chunks:
        return

    collection = (
        init_collection(collection_name)
        if collection_name
        else (_active_collection or init_collection())
    )

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for chunk in chunks:
        ids.append(str(chunk.id))
        documents.append(chunk.text)
        metadatas.append(_normalize_metadata(chunk.metadata))

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )


def query(
    query_text: str,
    top_k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
    collection_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Performs semantic similarity search for the query text.
    Supports top_k limit and optional metadata filtering (Chroma `where` syntax).
    Returns a list of dicts: [{"id": ..., "text": ..., "metadata": ..., "distance": ...}].
    """
    collection = (
        init_collection(collection_name)
        if collection_name
        else (_active_collection or init_collection())
    )

    query_kwargs: Dict[str, Any] = {
        "query_texts": [query_text],
        "n_results": top_k
    }
    if metadata_filter:
        query_kwargs["where"] = metadata_filter

    raw_results = collection.query(**query_kwargs)

    results: List[Dict[str, Any]] = []
    if raw_results and "ids" in raw_results and raw_results["ids"]:
        ids = raw_results["ids"][0]
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = (
            raw_results.get("distances", [[]])[0]
            if raw_results.get("distances")
            else [None] * len(ids)
        )

        for i in range(len(ids)):
            results.append({
                "id": ids[i],
                "text": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None
            })

    return results


def delete_by_source(
    source_id: str,
    collection_name: Optional[str] = None
) -> None:
    """
    Deletes all chunks belonging to the specified source (matching source_file or source_id).
    """
    collection = (
        init_collection(collection_name)
        if collection_name
        else (_active_collection or init_collection())
    )

    # Delete where source_file matches source_id (matching ChunkMetadata field)
    try:
        collection.delete(where={"source_file": source_id})
    except Exception:
        pass

    # Also handle if callers passed source_id as metadata key
    try:
        collection.delete(where={"source_id": source_id})
    except Exception:
        pass


class VectorStoreService:
    """
    Convenience wrapper class for object-oriented vector store access.
    """
    def __init__(self, collection_name: str = DEFAULT_COLLECTION_NAME):
        self.collection_name = collection_name
        self.collection = init_collection(collection_name)

    def add_chunks(self, chunks: List[ChunkRecord]) -> None:
        add_chunks(chunks, collection_name=self.collection_name)

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        return query(
            query_text=query_text,
            top_k=top_k,
            metadata_filter=metadata_filter,
            collection_name=self.collection_name
        )

    def delete_by_source(self, source_id: str) -> None:
        delete_by_source(source_id, collection_name=self.collection_name)
