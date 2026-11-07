import os
import sys
import io
from pypdf import PdfWriter
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.models import User
from app.services.ingestion import (
    extract_pdf_pages,
    process_and_ingest_document,
    get_indexed_sources,
    delete_source_chunks,
    _count_tokens,
    _text_splitter
)
from app.services.vector_store import query, init_collection


def create_sample_pdf() -> bytes:
    """Generates a simple 2-page sample PDF in memory for testing."""
    writer = PdfWriter()
    # Page 1
    page1 = writer.add_blank_page(width=612, height=792)
    # Page 2
    page2 = writer.add_blank_page(width=612, height=792)
    
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def run_verification():
    print("=" * 60)
    print("      EduSense - Task 2: Ingestion Pipeline Verification")
    print("=" * 60)

    # 1. Test Token Counting & Splitter Configuration
    print("\n[1/6] Testing Token Counter & Splitter Config...")
    sample_text = "EduSense AI is an advanced adaptive learning platform using multi-agent technology. " * 50
    tokens = _count_tokens(sample_text)
    print(f"  - Sample text token count: {tokens}")
    assert tokens > 0, "Token counting returned 0"

    chunks = _text_splitter.split_text(sample_text)
    print(f"  - Split into {len(chunks)} chunk(s)")
    for idx, chunk in enumerate(chunks):
        c_tokens = _count_tokens(chunk)
        print(f"    * Chunk {idx+1} token length: {c_tokens}")
        assert 50 <= c_tokens <= 1100, f"Unexpected chunk token length: {c_tokens}"

    # 2. Ingest Sample Document
    print("\n[2/6] Ingesting Sample Text Document...")
    doc_text = (
        "Quantum physics is the study of matter and energy at the most fundamental level. "
        "It aims to uncover the properties and behaviors of the very building blocks of nature. "
        "While many quantum experiments examine very small objects, such as electrons and photons, "
        "quantum phenomena are all around us, acting on every scale."
    ) * 15

    doc_bytes = doc_text.encode("utf-8")
    filename = "quantum_mechanics_101.txt"
    subject = "Physics"
    grade_level = "11"
    topic = "Quantum Mechanics"

    result = process_and_ingest_document(
        file_bytes=doc_bytes,
        filename=filename,
        subject=subject,
        grade_level=grade_level,
        topic=topic,
        source_id=filename
    )
    print(f"  - Ingestion result: {result}")
    assert result["status"] == "success"
    assert result["chunk_count"] > 0
    assert result["subject"] == subject
    assert result["grade_level"] == grade_level
    assert result["topic"] == topic

    # 3. Query Vector Store for Ingested Document
    print("\n[3/6] Querying Vector Store for Ingested Chunks...")
    q_res = query("fundamental level of matter and energy", top_k=2)
    assert len(q_res) > 0, "No query results returned after ingestion!"
    match = q_res[0]
    print(f"  - Top Match ID:       {match['id']}")
    print(f"  - Top Match Subject:  {match['metadata'].get('subject')}")
    print(f"  - Top Match Topic:    {match['metadata'].get('topic')}")
    assert match['metadata'].get('subject') == subject
    assert match['metadata'].get('topic') == topic

    # 4. List Indexed Sources
    print("\n[4/6] Testing get_indexed_sources()...")
    sources = get_indexed_sources()
    print(f"  - Indexed Sources Count: {len(sources)}")
    found = False
    for s in sources:
        print(f"    * Source ID: {s['source_id']} | Filename: {s['filename']} | Chunks: {s['chunk_count']} | Subject: {s['subject']}")
        if s['source_id'] == filename:
            found = True
            assert s['subject'] == subject
            assert s['grade_level'] == grade_level
            assert s['topic'] == topic
            assert s['chunk_count'] > 0
    assert found, f"Source '{filename}' was not found in get_indexed_sources()!"

    # 5. Test API Endpoints with TestClient
    print("\n[5/6] Testing FastAPI RAG Endpoints (POST, GET, DELETE)...")
    from app.db.seed import init_db
    from app.core.security import hash_password
    init_db(seed=True)

    db = SessionLocal()
    instructor = db.query(User).filter(User.role == "instructor").first()
    if not instructor:
        instructor = User(
            name="Test Instructor",
            email="test_instructor@edusense.io",
            password_hash=hash_password("password123"),
            role="instructor"
        )
        db.add(instructor)
        db.commit()
        db.refresh(instructor)

    email = instructor.email
    role = instructor.role
    db.close()

    token = create_access_token(subject=email, role=role)
    headers = {"Authorization": f"Bearer {token}"}



    client = TestClient(app)

    # Test POST /api/rag/ingest
    files = {"file": ("algebra_basics.txt", b"Algebra is a branch of mathematics dealing with symbols and rules for manipulating those symbols.", "text/plain")}
    data = {"subject": "Mathematics", "grade_level": "9", "topic": "Algebra"}

    response = client.post("/api/rag/ingest", headers=headers, files=files, data=data)
    print(f"  - POST /api/rag/ingest status: {response.status_code}")
    assert response.status_code == 200, f"Ingest endpoint failed: {response.text}"
    resp_json = response.json()
    print(f"  - Ingest response: {resp_json}")
    assert resp_json["status"] in ["success", "queued"]

    # Test GET /api/rag/sources
    sources_resp = client.get("/api/rag/sources", headers=headers)
    print(f"  - GET /api/rag/sources status: {sources_resp.status_code}")
    assert sources_resp.status_code == 200
    sources_list = sources_resp.json()
    print(f"  - Returned {len(sources_list)} source(s)")

    # Test DELETE /api/rag/sources/{source_id}
    del_resp = client.delete("/api/rag/sources/algebra_basics.txt", headers=headers)
    print(f"  - DELETE /api/rag/sources/algebra_basics.txt status: {del_resp.status_code}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"

    # 6. Delete Original Source Chunks & Verify Cleanup
    print("\n[6/6] Cleaning up original test source chunks...")
    delete_source_chunks(filename)
    sources_after = get_indexed_sources()
    rem_sources = [s for s in sources_after if s['source_id'] == filename]
    assert len(rem_sources) == 0, f"Source '{filename}' was not deleted from collection!"
    print(f"  - Source '{filename}' successfully deleted!")

    print("\n" + "=" * 60)
    print("   [SUCCESS] ALL TASK 2 VERIFICATION CHECKS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_verification()
    except Exception as e:
        print(f"\n[ERROR] Task 2 verification failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
