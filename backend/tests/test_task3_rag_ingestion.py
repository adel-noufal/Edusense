import os
import sys
import io
import time
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from app.main import app
from app.services.file_validation import validate_file_signature
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.models import User

client = TestClient(app)

def create_test_pdf(text_content="Introduction to Physics and Classical Mechanics."):
    """Creates a valid test PDF with real text using ReportLab."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, text_content)
    c.drawString(100, 730, "Sir Isaac Newton formulated the three fundamental laws of motion.")
    c.drawString(100, 710, "In an isolated system, momentum is always conserved.")
    c.save()
    return buf.getvalue()

def get_auth_headers():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.role.in_(["instructor", "admin"])).first()
        if not user:
            user = db.query(User).first()
        token = create_access_token(subject=user.email, role=user.role)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()

def test_file_signature_validation():
    print("\n--- 1. Testing File Signature Validation ---")
    valid_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"
    ok, msg = validate_file_signature("doc.pdf", valid_pdf_bytes)
    assert ok is True
    print("âœ“ Valid PDF signature passed:", msg)

    # Spoofed executable (.exe pretending to be .pdf)
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"
    ok, msg = validate_file_signature("malicious.pdf", fake_exe)
    assert ok is False
    print(f"âœ“ Spoofed PE/MZ binary correctly rejected: {msg}")

    # Spoofed ELF binary
    fake_elf = b"\x7fELF\x02\x01\x01\x00"
    ok, msg = validate_file_signature("malicious.pdf", fake_elf)
    assert ok is False
    print(f"âœ“ Spoofed ELF binary correctly rejected: {msg}")

    # Malicious script inside text
    malicious_script = b"<script>alert('xss')</script>"
    ok, msg = validate_file_signature("notes.txt", malicious_script)
    assert ok is False
    print(f"âœ“ Script tag in text file correctly rejected: {msg}")

def test_rag_ingest_rejection():
    print("\n--- 2. Testing API Rejecting Spoofed Files ---")
    headers = get_auth_headers()
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"
    resp = client.post(
        "/api/rag/ingest",
        headers=headers,
        data={"subject": "Science", "grade_level": "Grade 10", "topic": "Physics"},
        files={"file": ("fake_document.pdf", io.BytesIO(fake_exe), "application/pdf")},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "File validation failed" in resp.json()["detail"]
    print(f"âœ“ API correctly returned 400 for spoofed upload: {resp.json()['detail']}")

def test_rag_ingest_and_lifecycle():
    print("\n--- 3. Testing Standard & Background Ingest, Preview, and Cleanup ---")
    headers = get_auth_headers()
    pdf_bytes = create_test_pdf()
    assert pdf_bytes.startswith(b"%PDF"), "Must be a valid PDF format"

    # Test 3a: Async / Background ingestion
    resp = client.post(
        "/api/rag/ingest",
        headers=headers,
        data={
            "subject": "Physics",
            "grade_level": "Grade 11",
            "topic": "Mechanics",
            "is_async": "true",
        },
        files={"file": ("test_async_guide.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["status"] in ("queued", "completed")
    job_id = data.get("job_id")
    source_id = data.get("source_id")
    print(f"âœ“ Ingest triggered with job_id: {job_id}, response status: {data['status']}")

    # If job is tracked, poll status endpoint
    if job_id:
        for _ in range(30):
            s_resp = client.get(f"/api/rag/ingest/status/{job_id}", headers=headers)
            assert s_resp.status_code == 200
            s_data = s_resp.json()
            if s_data["status"] == "completed":
                print(f"âœ“ Background ingestion job completed: {s_data.get('message')}")
                break
            elif s_data["status"] == "failed":
                pytest.fail(f"Background ingestion failed: {s_data}")
            time.sleep(0.5)
        else:
            pytest.fail("Background ingestion timed out")

    # Test 3b: Verify source listing returns file metadata
    sources_resp = client.get("/api/rag/sources", headers=headers)
    assert sources_resp.status_code == 200
    sources_data = sources_resp.json()
    sources = sources_data if isinstance(sources_data, list) else sources_data.get("sources", [])
    matching = [s for s in sources if s.get("source_id") == source_id or s.get("source_file") == "test_async_guide.pdf"]
    assert len(matching) > 0, f"Source test_async_guide.pdf must appear in indexed sources: {sources}"
    src = matching[0]
    target_id = src.get("source_id")
    assert src.get("has_file") is True
    assert src.get("file_url") is not None
    print(f"âœ“ Source listed with has_file={src.get('has_file')}, file_url={src.get('file_url')}, chunk_count={src.get('chunk_count')}")

    # Test 3c: Preview endpoint
    preview_resp = client.get(f"/api/rag/sources/{target_id}/preview", headers=headers)
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert "source_id" in preview_data
    assert "sample_chunks" in preview_data
    print(f"âœ“ Preview retrieved successfully with {len(preview_data.get('sample_chunks', []))} sample chunks")

    # Test 3d: File download/view endpoint
    file_resp = client.get(f"/api/rag/sources/{target_id}/file", headers=headers)
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "application/pdf"
    assert file_resp.content.startswith(b"%PDF")
    print(f"âœ“ File view endpoint served {len(file_resp.content)} bytes of application/pdf")

    # Test 3e: Clean deletion of vector chunks and physical file
    del_resp = client.delete(f"/api/rag/sources/{target_id}", headers=headers)
    assert del_resp.status_code == 200
    print(f"âœ“ Deleted source: {del_resp.json()}")

    # Check file is removed from disk
    file_after_del = client.get(f"/api/rag/sources/{target_id}/file", headers=headers)
    assert file_after_del.status_code == 404
    print("âœ“ Verification complete: file correctly removed from disk and returned 404")

if __name__ == "__main__":
    test_file_signature_validation()
    test_rag_ingest_rejection()
    test_rag_ingest_and_lifecycle()
    print("\nALL TASK 3 TESTS PASSED!")
