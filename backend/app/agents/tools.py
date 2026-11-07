from typing import Any, Dict, List, Optional
import json
import urllib.request
import urllib.error
from app.core.config import get_settings
from app.services import vector_store


def Web_Search_Tool(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_answer: bool = True,
    include_raw_content: bool = False,
) -> List[Dict[str, Any]]:
    """
    Searches the web using Tavily API for current information.
    Returns: [{title, url, content, score}, ...]
    """
    settings = get_settings()
    api_key = getattr(settings, "tavily_api_key", "") or getattr(settings, "TAVILY_API_KEY", "")

    if not api_key:
        print("[Web Search] Tavily API key not configured; returning empty results.")
        return []

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
    }

    try:
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))

        results = result.get("results", [])
        formatted = []
        for item in results:
            formatted.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0.0),
            })
        return formatted
    except urllib.error.HTTPError as e:
        print(f"[Web Search] HTTP error: {e.code} - {e.reason}")
        return []
    except urllib.error.URLError as e:
        print(f"[Web Search] Network error: {e.reason}")
        return []
    except Exception as e:
        print(f"[Web Search] Unexpected error: {e}")
        return []


# Gemini Function Calling Tool Declaration Schema
WEB_SEARCH_TOOL_SCHEMA = {
    "name": "Web_Search_Tool",
    "description": (
        "Searches the web using Tavily API for current information, news, "
        "and up-to-date facts not available in the local knowledge base."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "The search query to find current information on the web."
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Maximum number of results to return (default: 5)."
            },
            "search_depth": {
                "type": "STRING",
                "description": "Search depth: 'basic' for fast results, 'advanced' for comprehensive (default: basic).",
                "enum": ["basic", "advanced"]
            }
        },
        "required": ["query"]
    }
}


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
