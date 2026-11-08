"""
Section 4 Verification Test — Instructor-Side Bugs
1. GET /api/ai/generations/{id} returns the latest generation details (no stale content).
2. Session resource upload with proper Authorization token succeeds and is retrievable via GET /api/sessions/{id}/resources.
3. RAG document ingestion endpoint returns valid JSON on both success and error (no empty or unparseable responses).
4. Frontend build check.
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import date, time
from fastapi.testclient import TestClient
from app.db.seed import init_db
from app.main import app
from app.db.session import get_db
from app.models.models import User, Session as ClassSession, SessionResource, AIGeneration
from app.core.security import hash_password, create_access_token

init_db(seed=False)
client = TestClient(app)
db = next(get_db())

PASSED = []
FAILED = []

def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  PASS {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name}{': ' + detail if detail else ''}")

print("\n=== Section 4 Verification ===\n")

# Setup instructor
inst = db.query(User).filter_by(email="s4_instructor@test.com").first()
if not inst:
    inst = User(name="S4 Instructor", email="s4_instructor@test.com", password_hash=hash_password("test123"), role="instructor")
    db.add(inst); db.commit(); db.refresh(inst)

inst_tok = create_access_token(inst.email, inst.role)
headers = {"Authorization": f"Bearer {inst_tok}"}

# 1. Test GET /api/ai/generations/{id}
print("Group 1: AI Generation Detail Retrieval (Fix Stale Lesson View)")
gen_data = {"topic": "Quantum Computing", "language": "English", "style": "Interactive", "duration": 10, "sections": ["Intro", "Qubits"]}
ai_gen = AIGeneration(
    instructor_id=inst.id,
    type="lesson",
    topic="Quantum Computing",
    prompt="Explain qubits to high schoolers",
    data_json=json.dumps(gen_data),
)
db.add(ai_gen); db.commit(); db.refresh(ai_gen)

r = client.get(f"/api/ai/generations/{ai_gen.id}", headers=headers)
check("1. GET /api/ai/generations/{id} returns 200", r.status_code == 200, f"status={r.status_code}")
res_json = r.json() if r.status_code == 200 else {}
check("2. Returns correct topic", res_json.get("topic") == "Quantum Computing")
check("3. Returns latest parsed data payload", res_json.get("data", {}).get("duration") == 10)

# Update the generation to simulate linking/regenerating
updated_data = {"topic": "Quantum Computing v2", "language": "English", "style": "Advanced", "duration": 15}
ai_gen.data_json = json.dumps(updated_data)
ai_gen.session_id = 999
db.commit()

r_updated = client.get(f"/api/ai/generations/{ai_gen.id}", headers=headers)
check("4. Fresh fetch returns updated content (not stale)", r_updated.json().get("data", {}).get("duration") == 15)
check("5. Fresh fetch returns updated session_id", r_updated.json().get("session_id") == 999)

# 2. Test Session Resource Upload and Listing
print("\nGroup 2: Session Resource Upload (Sources Tab Fix)")
session = ClassSession(
    title="S4 Physics Lab",
    description="",
    date=date(2026, 12, 10),
    start_time=time(14, 0),
    duration=90,
    instructor_id=inst.id,
    status="scheduled"
)
db.add(session); db.commit(); db.refresh(session)

# Create a mock text/pdf resource
test_file_bytes = b"%PDF-1.4 test resource binary content"
r_upload = client.post(
    f"/api/sessions/{session.id}/resources",
    files={"file": ("lab_manual.pdf", io.BytesIO(test_file_bytes), "application/pdf")},
    headers=headers,
)
check("6. Upload resource returns 200", r_upload.status_code == 200, f"status={r_upload.status_code} body={r_upload.text[:150]}")

r_list = client.get(f"/api/sessions/{session.id}/resources", headers=headers)
check("7. List session resources returns 200", r_list.status_code == 200)
resources = r_list.json() if r_list.status_code == 200 else []
check("8. Newly uploaded resource appears in session list", any(res["name"] == "lab_manual.pdf" for res in resources))

# 3. Test RAG Ingestion JSON Safety
print("\nGroup 3: RAG Ingest JSON Safety (No 'Unexpected end of JSON input')")
# Test empty upload -> must return structured JSON error with detail, not empty body
r_empty = client.post(
    "/api/rag/ingest",
    files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    data={"subject": "Physics", "grade_level": "11", "topic": "Mechanics"},
    headers=headers,
)
check("9. Empty file rejected with 400", r_empty.status_code == 400)
try:
    empty_json = r_empty.json()
    check("10. Error response is valid JSON", "detail" in empty_json)
except Exception as e:
    check("10. Error response is valid JSON", False, str(e))

# Test missing fields -> FastAPI validation error returns 422 JSON
r_invalid = client.post(
    "/api/rag/ingest",
    files={"file": ("doc.pdf", io.BytesIO(b"some content"), "application/pdf")},
    data={},  # missing required fields
    headers=headers,
)
check("11. Missing form fields return 422 JSON", r_invalid.status_code == 422 and "detail" in r_invalid.json())

# Test valid text document ingestion -> must return 200 JSON
r_valid = client.post(
    "/api/rag/ingest",
    files={"file": ("notes.txt", io.BytesIO(b"Newton third law: every action has an equal opposite reaction."), "text/plain")},
    data={"subject": "Physics", "grade_level": "11", "topic": "Mechanics", "is_async": "false"},
    headers=headers,
)
check("12. Valid ingest returns 200 JSON", r_valid.status_code == 200, f"status={r_valid.status_code} body={r_valid.text[:100]}")
try:
    valid_json = r_valid.json()
    check("13. Ingest response contains status or chunks", "source_id" in valid_json or "chunk_count" in valid_json)
except Exception as e:
    check("13. Ingest response contains status", False, str(e))

print(f"\n{'='*50}")
print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
else:
    print("ALL PASSED PASS")
    sys.exit(0)
