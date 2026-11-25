import os
from pathlib import Path
os.environ["ANONYMIZED_TELEMETRY"] = "False"
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import get_settings

# Tests export EDUSENSE_RAG_COLLECTION so their fixtures never land in the live
# Knowledge Base collection (U7). Production keeps the pinned name.
DEFAULT_COLLECTION_NAME = os.environ.get("EDUSENSE_RAG_COLLECTION", "edusense_knowledge")

_client_instance: Optional[chromadb.PersistentClient] = None
_embedding_function = None
_active_collection: Optional[chromadb.Collection] = None


def _embedding_name(embedding_fn) -> str:
    """Best-effort embedding function identifier used in conflict messages."""
    try:
        return str(embedding_fn.name())
    except Exception:  # noqa: BLE001
        return type(embedding_fn).__name__


def _persisted_embedding_name(collection) -> Optional[str]:
    """Read the embedding function name stored in the Chroma collection config."""
    # Chroma exposes the persisted config in a few shapes depending on version.
    candidates = []
    raw = getattr(collection, "configuration_json", None)
    if isinstance(raw, str) and raw:
        try:
            candidates.append(json.loads(raw))
        except Exception:  # noqa: BLE001
            pass
    elif isinstance(raw, dict):
        candidates.append(raw)
    model = getattr(collection, "_model", None)
    if model is not None and isinstance(getattr(model, "configuration_json", None), dict):
        candidates.append(model.configuration_json)

    for config in candidates:
        ef = config.get("embedding_function")
        if isinstance(ef, dict) and ef.get("name"):
            return str(ef["name"])
    configuration = getattr(collection, "configuration", None) or {}
    ef = configuration.get("embedding_function") if isinstance(configuration, dict) else None
    if ef is not None:
        type_name = type(ef).__name__
        if type_name.startswith("SentenceTransformer"):
            return "sentence_transformer"
        if type_name.startswith("ONNX"):
            return "onnx_mini_lm_l6_v2"
    return None


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
    Returns the local SentenceTransformerEmbeddingFunction for all-MiniLM-L6-v2.

    The persisted Chroma collection was built with `sentence_transformer`.
    Silently switching to Chroma's ONNX implementation changes the embedding
    space, so Chroma refuses to open the collection and the Knowledge Base
    appears empty. Therefore this function NEVER falls back on its own: if
    sentence-transformers cannot be imported it raises a readable error that
    explains how to fix the venv. A deliberate fallback is only possible by
    setting EDUSENSE_ALLOW_ONNX_EMBEDDING=1, and even then the persisted
    collection must be re-indexed separately.
    """
    global _embedding_function
    if _embedding_function is None or model_name is not None:
        settings = get_settings()
        selected_model = model_name or settings.embedding_model
        # Keep the model inside the project so the folder can be copied to an
        # offline PC: SentenceTransformer honours SENTENCE_TRANSFORMERS_HOME.
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "models"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache_dir))
        try:
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=selected_model, cache_folder=str(cache_dir)
            )
        except Exception as exc:  # noqa: BLE001 - re-raised with guidance
            if os.environ.get("EDUSENSE_ALLOW_ONNX_EMBEDDING", "0") != "1":
                offline = (os.environ.get("HF_HUB_OFFLINE") == "1"
                           or os.environ.get("TRANSFORMERS_OFFLINE") == "1")
                if offline or "connect" in str(exc).lower() or "offline" in str(exc).lower():
                    raise RuntimeError(
                        f"Embedding model {selected_model!r} is not cached; connect once to "
                        "download it (start-all.bat does this), then the Knowledge Base "
                        "works offline."
                    ) from exc
                raise RuntimeError(
                    "The sentence-transformers embedding function could not be loaded "
                    f"({type(exc).__name__}: {exc}). The Knowledge Base collection was index"
                    "ed with sentence_transformer, so switching embedding models would "
                    "produce invalid results. Fix the backend venv ("
                    '`pip install --force-reinstall -r requirements.txt`) and restart. '
                    "Set EDUSENSE_ALLOW_ONNX_EMBEDDING=1 only to start a brand-new collection."
                ) from exc
            embedding_fn = embedding_functions.ONNXMiniLM_L6_V2()

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

    # Open an existing collection with the embedding function it was persisted
    # with. Passing a different function makes Chroma raise
    # "Embedding function conflict: new: onnx_mini_lm_l6_v2 vs persisted:
    # sentence_transformer", which used to surface as an empty Knowledge Base.
    existing = {c.name if hasattr(c, "name") else str(c) for c in client.list_collections()}
    if name in existing:
        collection = client.get_collection(name)
        persisted = _persisted_embedding_name(collection)
        if persisted and persisted != _embedding_name(embedding_fn):
            raise RuntimeError(
                f"Embedding function conflict for collection '{name}': persisted "
                f"'{persisted}' but the active function is '{_embedding_name(embedding_fn)}'. "
                "Refusing to mix embedding spaces. Fix the venv so the same model loads "
                "(pip install --force-reinstall -r requirements.txt)."
            )
    else:
        collection = client.create_collection(
            name=name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
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

    # Batch upsert to support large files with thousands of chunks without exceeding ChromaDB/SQLite limits
    BATCH_SIZE = 200
    for i in range(0, len(ids), BATCH_SIZE):
        collection.upsert(
            ids=ids[i:i + BATCH_SIZE],
            documents=documents[i:i + BATCH_SIZE],
            metadatas=metadatas[i:i + BATCH_SIZE]
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


def get_by_source(
    source_id: str,
    collection_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return all indexed chunks for a document source without vector ranking."""
    collection = (
        init_collection(collection_name)
        if collection_name
        else (_active_collection or init_collection())
    )

    for metadata_key in ("source_file", "source_id"):
        raw_results = collection.get(
            where={metadata_key: source_id},
            include=["documents", "metadatas"],
        )
        ids = raw_results.get("ids", [])
        if ids:
            documents = raw_results.get("documents") or []
            metadatas = raw_results.get("metadatas") or []
            return [
                {
                    "id": chunk_id,
                    "text": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": None,
                }
                for index, chunk_id in enumerate(ids)
            ]
    return []


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
