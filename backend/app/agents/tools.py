from typing import Any, Dict, List, Optional
from app.core.config import get_settings
from app.services import vector_store


def RAG_Search_Tool(
    query: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    top_k: int = 5,
    collection_name: Optional[str] = None,
    min_score: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Searches the EduSense vector knowledge base for relevant educational chunks
    matching the query, filtered by subject and grade level.
    Returns: [{text, source_file, page, subject, grade_level, topic, score}, ...]
    """
    settings = get_settings()
    threshold = min_score if min_score is not None else settings.rag_min_score

    # Build Chroma metadata filter
    filters = []
    if subject:
        filters.append({"subject": subject})
    if grade_level:
        filters.append({"grade_level": str(grade_level)})

    metadata_filter = None
    if len(filters) == 1:
        metadata_filter = filters[0]
    elif len(filters) > 1:
        metadata_filter = {"$and": filters}

    # Query vector store
    raw_results = vector_store.query(
        query_text=query,
        top_k=top_k,
        metadata_filter=metadata_filter,
        collection_name=collection_name
    )

    formatted_results: List[Dict[str, Any]] = []

    for item in raw_results:
        dist = item.get("distance")
        # Cosine similarity score = 1 - distance (clamped to [0, 1])
        if dist is not None:
            score = round(max(0.0, min(1.0, 1.0 - float(dist))), 4)
        else:
            score = 1.0

        if score < threshold:
            continue

        meta = item.get("metadata", {}) or {}
        formatted_results.append({
            "text": item.get("text", ""),
            "source_file": str(meta.get("source_file") or meta.get("source_id") or meta.get("filename") or ""),
            "page": meta.get("page", 1),
            "subject": str(meta.get("subject", "")),
            "grade_level": str(meta.get("grade_level", "")),
            "topic": str(meta.get("topic", "")),
            "score": score
        })

    # Sort results descending by score
    formatted_results.sort(key=lambda x: x["score"], reverse=True)
    return formatted_results[:top_k]


# Gemini Function Calling Tool Declaration Schema
RAG_SEARCH_TOOL_SCHEMA = {
    "name": "RAG_Search_Tool",
    "description": (
        "Searches the EduSense RAG vector knowledge base for relevant educational textbook chunks "
        "and course materials based on query, subject, and grade level."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "The search query topic or question to retrieve contextual knowledge for."
            },
            "subject": {
                "type": "STRING",
                "description": "Optional academic subject filter (e.g., Mathematics, Physics, Biology)."
            },
            "grade_level": {
                "type": "STRING",
                "description": "Optional grade level filter (e.g., 9, 10, 11, 12)."
            },
            "top_k": {
                "type": "INTEGER",
                "description": "Maximum number of relevant chunks to retrieve (default: 5)."
            }
        },
        "required": ["query"]
    }
}
