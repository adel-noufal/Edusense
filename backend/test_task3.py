import os
import sys

from app.core.config import get_settings
from app.services.vector_store import (
    ChunkMetadata,
    ChunkRecord,
    add_chunks,
    init_collection,
    delete_by_source,
)
from app.agents.tools import RAG_Search_Tool, RAG_SEARCH_TOOL_SCHEMA


def run_verification():
    print("=" * 60)
    print("      EduSense - Task 3: RAG Search Tool Verification")
    print("=" * 60)

    # 1. Check Settings & Schema
    print("\n[1/5] Checking Settings & Gemini Tool Schema...")
    settings = get_settings()
    print(f"  - RAG_MIN_SCORE: {settings.rag_min_score}")
    print(f"  - Tool Schema Name: {RAG_SEARCH_TOOL_SCHEMA['name']}")
    assert settings.rag_min_score == 0.6
    assert RAG_SEARCH_TOOL_SCHEMA["name"] == "RAG_Search_Tool"
    assert "query" in RAG_SEARCH_TOOL_SCHEMA["parameters"]["required"]

    # 2. Seed Test Collection
    test_collection_name = "test_task3_rag_search_collection"
    print(f"\n[2/5] Seeding Test Collection '{test_collection_name}'...")
    col = init_collection(test_collection_name)

    chunks = [
        ChunkRecord(
            id="t3_chunk_bio_1",
            text="Cellular respiration converts glucose and oxygen into ATP, water, and carbon dioxide.",
            metadata=ChunkMetadata(
                subject="Biology",
                grade_level="10",
                topic="Cellular Respiration",
                source_file="biology_ch3.pdf",
                page=45,
            ),
        ),
        ChunkRecord(
            id="t3_chunk_physics_1",
            text="Newton's second law states that force equals mass times acceleration (F = ma).",
            metadata=ChunkMetadata(
                subject="Physics",
                grade_level="11",
                topic="Mechanics",
                source_file="physics_ch1.pdf",
                page=12,
            ),
        ),
        ChunkRecord(
            id="t3_chunk_math_1",
            text="The quadratic formula calculates roots of polynomial equations of second degree.",
            metadata=ChunkMetadata(
                subject="Mathematics",
                grade_level="10",
                topic="Algebra",
                source_file="math_ch2.pdf",
                page=30,
            ),
        ),
    ]

    add_chunks(chunks, collection_name=test_collection_name)
    print(f"  - Chunks added successfully! Collection count: {col.count()}")

    # 3. Test RAG_Search_Tool basic query & ranking with min_score=0.1
    print("\n[3/6] Testing RAG_Search_Tool query & ranking...")
    results = RAG_Search_Tool(
        query="cellular energy ATP production",
        top_k=2,
        collection_name=test_collection_name,
        min_score=0.1
    )
    print(f"  - Returned {len(results)} result(s)")
    assert len(results) > 0, "No results returned for general query!"
    top_res = results[0]
    print(f"  - Top Match Text:   {top_res['text'][:60]}...")
    print(f"  - Top Match Subject: {top_res['subject']}")
    print(f"  - Top Match Score:   {top_res['score']}")
    assert top_res["subject"] == "Biology"
    assert top_res["score"] > 0.0

    # 3b. Test RAG_Search_Tool with DEFAULT RAG_MIN_SCORE (0.6)
    print("\n[3b/6] Testing RAG_Search_Tool with DEFAULT threshold RAG_MIN_SCORE (0.6)...")
    default_res = RAG_Search_Tool(
        query="cellular respiration ATP energy",
        collection_name=test_collection_name
        # Uses default min_score=None -> settings.rag_min_score (0.6)
    )
    print(f"  - Results count with default RAG_MIN_SCORE=0.6: {len(default_res)}")
    for r in default_res:
        print(f"    * Text: '{r['text'][:50]}...' | Score: {r['score']} (>= 0.6 threshold: PASS)")
        assert r["score"] >= 0.6


    # 4. Test RAG_Search_Tool metadata filtering (subject & grade_level)
    print("\n[4/5] Testing metadata filtering (subject='Physics', grade_level='11')...")
    filtered_res = RAG_Search_Tool(
        query="force mass motion equation",
        subject="Physics",
        grade_level="11",
        top_k=5,
        collection_name=test_collection_name,
        min_score=0.1
    )
    print(f"  - Filtered Results Count: {len(filtered_res)}")
    for r in filtered_res:
        print(f"    * Text: {r['text'][:50]}... | Subject: {r['subject']} | Grade: {r['grade_level']} | Score: {r['score']}")
        assert r["subject"] == "Physics"
        assert r["grade_level"] == "11"

    # 5. Clean up test chunks
    print("\n[5/5] Cleaning up test collection...")
    delete_by_source("biology_ch3.pdf", collection_name=test_collection_name)
    delete_by_source("physics_ch1.pdf", collection_name=test_collection_name)
    delete_by_source("math_ch2.pdf", collection_name=test_collection_name)
    print("  - Cleanup complete!")

    print("\n" + "=" * 60)
    print("   [SUCCESS] ALL TASK 3 VERIFICATION CHECKS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_verification()
    except Exception as e:
        print(f"\n[ERROR] Task 3 verification failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
