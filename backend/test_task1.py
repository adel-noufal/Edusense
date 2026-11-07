import os
import sys

from app.core.config import get_settings
from app.services.vector_store import (
    ChunkMetadata,
    ChunkRecord,
    add_chunks,
    delete_by_source,
    get_client,
    init_collection,
    query,
)


def run_verification():
    print("=" * 60)
    print("      EduSense - Task 1: Vector Store Verification")
    print("=" * 60)

    # 1. Settings Check
    print("\n[1/7] Checking Settings...")
    settings = get_settings()
    print(f"  - CHROMA_PERSIST_DIR: {settings.chroma_persist_dir}")
    print(f"  - EMBEDDING_MODEL:    {settings.embedding_model}")

    # 2. Collection Initialization
    print("\n[2/7] Initializing Persistent Collection...")
    col = init_collection("test_verification_collection")
    print(f"  - Collection Name:    {col.name}")
    print(f"  - Initial Count:      {col.count()}")

    # 3. Adding Chunks
    print("\n[3/7] Adding Sample Chunks with Metadata...")
    chunks = [
        ChunkRecord(
            id="chunk_bio_1",
            text="Photosynthesis is the process by which green plants convert sunlight into chemical energy.",
            metadata=ChunkMetadata(
                subject="Biology",
                grade_level="10",
                topic="Photosynthesis",
                source_file="biology_textbook.pdf",
                page=42,
            ),
        ),
        ChunkRecord(
            id="chunk_bio_2",
            text="Mitochondria are membrane-bound cell organelles that generate chemical energy for cellular activities.",
            metadata=ChunkMetadata(
                subject="Biology",
                grade_level="10",
                topic="Cell Biology",
                source_file="biology_textbook.pdf",
                page=58,
            ),
        ),
        ChunkRecord(
            id="chunk_cs_1",
            text="Binary search is an efficient divide-and-conquer algorithm for finding an element in a sorted list.",
            metadata=ChunkMetadata(
                subject="Computer Science",
                grade_level="12",
                topic="Algorithms",
                source_file="algorithms_intro.pdf",
                page=15,
            ),
        ),
    ]
    add_chunks(chunks, collection_name="test_verification_collection")
    total = col.count()
    print(f"  - Chunks added successfully! Total in collection: {total}")
    assert total >= 3, f"Expected at least 3 chunks, got {total}"

    # 4. Semantic Search
    print("\n[4/7] Testing Semantic Similarity Search...")
    search_query = "How do green plants turn light into energy?"
    print(f"  - Query: '{search_query}'")
    results = query(search_query, top_k=2, collection_name="test_verification_collection")
    assert len(results) > 0, "No results returned from query!"
    top_result = results[0]
    print(f"  - Top Match ID: {top_result['id']}")
    print(f"  - Topic:        {top_result['metadata'].get('topic')}")
    print(f"  - Distance:     {top_result['distance']:.4f}")
    assert top_result["id"] == "chunk_bio_1", f"Expected chunk_bio_1 as top match, got {top_result['id']}"

    # 5. Metadata Filtering
    print("\n[5/7] Testing Metadata Filtering (subject='Computer Science')...")
    filtered = query(
        "energy search process",
        top_k=5,
        metadata_filter={"subject": "Computer Science"},
        collection_name="test_verification_collection",
    )
    print(f"  - Filtered Results Count: {len(filtered)}")
    for r in filtered:
        print(f"    * ID: {r['id']} | Subject: {r['metadata'].get('subject')} | Topic: {r['metadata'].get('topic')}")
        assert r["metadata"].get("subject") == "Computer Science", "Metadata filtering failed!"

    # 6. delete_by_source
    print("\n[6/7] Testing delete_by_source('biology_textbook.pdf')...")
    delete_by_source("biology_textbook.pdf", collection_name="test_verification_collection")
    remaining = col.count()
    print(f"  - Remaining chunks in collection: {remaining}")
    assert remaining == 1, f"Expected 1 remaining chunk, got {remaining}"

    # 7. Persistence Verification
    print("\n[7/7] Verifying Local Disk Persistence...")
    target_dir = os.path.abspath(settings.chroma_persist_dir)
    sqlite_file = os.path.join(target_dir, "chroma.sqlite3")
    print(f"  - Chroma Dir:     {target_dir} -> Exists: {os.path.exists(target_dir)}")
    print(f"  - SQLite DB File: {sqlite_file} -> Exists: {os.path.exists(sqlite_file)}")
    assert os.path.exists(sqlite_file), "Chroma SQLite database was not found on disk!"

    print("\n" + "=" * 60)
    print("   [SUCCESS] ALL TASK 1 VERIFICATION CHECKS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_verification()
    except Exception as e:
        print(f"\n[ERROR] Verification failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
