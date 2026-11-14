"""
test_task8_chatbot_overhaul.py
Task 8 — AI Chatbot Overhaul: Separate Identity, Third API Key, Uploads & History
Tests:
  1. Config: chatbot_name, chatbot_persona, chatbot_gemini_api_key exist and third key support works
  2. GET /api/ai/chat/settings returns chatbot identity
  3. POST /api/ai/chat/upload handles text extraction & rejects empty file
  4. POST /api/ai/chat persists conversation_id, saves user & assistant messages, and injects persona
  5. POST /api/ai/chat supports file_context injection into orchestrator query
  6. GET /api/ai/chat/conversations lists conversations with message_count and preview
  7. GET /api/ai/chat/conversations/{id} returns message history
  8. DELETE /api/ai/chat/conversations/{id} cleans up conversation and returns 404 subsequently
"""
import io
import os
import sys
import uuid
from unittest.mock import patch, AsyncMock

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import Settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.models import User, ChatMessage as ChatMessageModel
from app.agents.orchestrator import OrchestratorResult

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    results.append((label, condition))

client = TestClient(app)

def get_auth_headers(email: str, role: str):
    token = create_access_token(subject=email, role=role)
    return {"Authorization": f"Bearer {token}"}

db = SessionLocal()
try:
    test_user = db.query(User).first()
    if not test_user:
        test_user = User(
            email="test_chatbot_user@edusense.com",
            password_hash="fakehash",
            name="Test Chatbot User",
            role="student"
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
    headers = get_auth_headers(test_user.email, test_user.role)
finally:
    db.close()

# ---------------------------------------------------------------------------
# Test 1: Config settings & Third API Key / Chatbot Key
# ---------------------------------------------------------------------------
print("\n--- Test 1: Chatbot Config & Dedicated / Third Key Support ---")
try:
    s = Settings(
        chatbot_name="Pythagoras AI",
        chatbot_persona="You are a geometry expert.",
        chatbot_gemini_api_key="dedicated-chatbot-key-12345",
        gemini_api_key="primary-key-1,secondary-key-2"
    )
    check("chatbot_name configurable", s.chatbot_name == "Pythagoras AI")
    check("chatbot_persona configurable", "geometry expert" in s.chatbot_persona)
    check("chatbot_gemini_api_key configurable", s.chatbot_gemini_api_key == "dedicated-chatbot-key-12345")
    all_keys = s.gemini_api_keys
    check("gemini_api_keys includes dedicated chatbot key", "dedicated-chatbot-key-12345" in all_keys)
    check("gemini_api_keys has at least 3 keys when configured", len(all_keys) >= 3, f"got {all_keys}")
except Exception as e:
    check("Config verification", False, str(e))

# ---------------------------------------------------------------------------
# Test 2: GET /api/ai/chat/settings
# ---------------------------------------------------------------------------
print("\n--- Test 2: GET /api/ai/chat/settings ---")
try:
    resp = client.get("/api/ai/chat/settings", headers=headers)
    check("status 200", resp.status_code == 200, f"got {resp.status_code}")
    data = resp.json()
    check("chatbot_name present in response", "chatbot_name" in data and bool(data["chatbot_name"]))
    check("persona_preview present in response", "persona_preview" in data)
except Exception as e:
    check("chat settings endpoint", False, str(e))

# ---------------------------------------------------------------------------
# Test 3: POST /api/ai/chat/upload
# ---------------------------------------------------------------------------
print("\n--- Test 3: POST /api/ai/chat/upload ---")
try:
    # 3a. Valid text upload
    file_bytes = b"Machine learning is a field of inquiry devoted to understanding and building methods that learn."
    files = {"file": ("notes.txt", io.BytesIO(file_bytes), "text/plain")}
    resp = client.post("/api/ai/chat/upload", headers=headers, files=files)
    check("valid text upload status 200", resp.status_code == 200, f"got {resp.status_code}")
    data = resp.json()
    check("filename matches", data.get("filename") == "notes.txt")
    check("char_count matches", data.get("char_count") == len(file_bytes))
    check("text extracted correctly", "Machine learning" in data.get("text", ""))

    # 3b. Empty file upload
    empty_files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    resp_empty = client.post("/api/ai/chat/upload", headers=headers, files=empty_files)
    check("empty file raises 422", resp_empty.status_code == 422, f"got {resp_empty.status_code}")
except Exception as e:
    check("chat upload endpoint", False, str(e))

# ---------------------------------------------------------------------------
# Tests 4 & 5: POST /api/ai/chat (Orchestrator Mocking & Persistence)
# ---------------------------------------------------------------------------
print("\n--- Tests 4 & 5: POST /api/ai/chat Conversation & Context Injection ---")
mock_result = OrchestratorResult(
    answer="Photosynthesis is the process by which green plants make food.",
    sources=["Biology Chapter 3"],
    web_sources=[{"title": "Photosynthesis Guide", "url": "https://example.com/photo"}],
    mode="online_rag_web_llm",
    rag_chunks_used=2,
    web_results_used=1,
    fallback_reason=None,
    unverified=False,
)

test_conv_id = None
captured_queries = []

async def _fake_run_async(query, subject=None, grade_level=None, conversation_history=None):
    captured_queries.append(query)
    return mock_result

try:
    with patch("app.api.ai.orchestrator._run_async", side_effect=_fake_run_async):
        # 4a. Initial chat without conversation_id
        payload = {
            "message": "Explain photosynthesis",
            "subject": "Biology",
            "grade_level": "10"
        }
        resp = client.post("/api/ai/chat", headers=headers, json=payload)
        check("chat status 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json()
        test_conv_id = data.get("conversation_id")
        check("returns conversation_id", bool(test_conv_id))
        check("returns answer", data.get("answer") == mock_result.answer)
        check("returns chatbot_name", bool(data.get("chatbot_name")))
        check("system persona injected into query", "[System: Your name is" in captured_queries[-1])

        # 4b. Follow-up chat with same conversation_id and file_context
        payload_2 = {
            "message": "Can you summarize the uploaded document?",
            "conversation_id": test_conv_id,
            "file_context": "Chapter 3 Summary: Light-dependent reactions occur in the thylakoid membrane."
        }
        resp_2 = client.post("/api/ai/chat", headers=headers, json=payload_2)
        check("follow-up status 200", resp_2.status_code == 200, f"got {resp_2.status_code}")
        check("conversation_id preserved", resp_2.json().get("conversation_id") == test_conv_id)
        check("file_context injected into query", "[Uploaded file context]" in captured_queries[-1])
        check("user question included in query", "Can you summarize the uploaded document?" in captured_queries[-1])

        # 4c. Verify database persistence
        db = SessionLocal()
        try:
            saved_msgs = db.query(ChatMessageModel).filter_by(
                conversation_id=test_conv_id,
                user_id=test_user.id
            ).order_by(ChatMessageModel.created_at.asc()).all()
            check("messages persisted in database", len(saved_msgs) == 4, f"got {len(saved_msgs)} messages")
            check("first message is user", saved_msgs[0].role == "user" and saved_msgs[0].content == "Explain photosynthesis")
            check("second message is assistant", saved_msgs[1].role == "assistant")
        finally:
            db.close()
except Exception as e:
    check("chat flow and persistence", False, str(e))

# ---------------------------------------------------------------------------
# Tests 6, 7 & 8: Conversations Management (List, Get, Delete)
# ---------------------------------------------------------------------------
print("\n--- Tests 6, 7 & 8: Conversations Management (List, Get, Delete) ---")
try:
    # Test 6: GET /api/ai/chat/conversations
    resp_list = client.get("/api/ai/chat/conversations", headers=headers)
    check("list conversations status 200", resp_list.status_code == 200, f"got {resp_list.status_code}")
    conv_list = resp_list.json()
    check("conversations is list", isinstance(conv_list, list))
    matching_conv = next((c for c in conv_list if c["conversation_id"] == test_conv_id), None)
    check("created conversation in list", matching_conv is not None)
    if matching_conv:
        check("message_count is 4", matching_conv.get("message_count") == 4, f"got {matching_conv.get('message_count')}")
        check("preview contains user query", "photosynthesis" in matching_conv.get("preview", "").lower())

    # Test 7: GET /api/ai/chat/conversations/{id}
    resp_get = client.get(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
    check("get conversation status 200", resp_get.status_code == 200, f"got {resp_get.status_code}")
    data_get = resp_get.json()
    check("get conversation messages count is 4", len(data_get.get("messages", [])) == 4)

    # Test 8: DELETE /api/ai/chat/conversations/{id}
    resp_del = client.delete(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
    check("delete conversation status 200", resp_del.status_code == 200, f"got {resp_del.status_code}")
    check("deleted count returned", resp_del.json().get("deleted") == 4)

    # Verify 404 after deletion
    resp_get_after = client.get(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
    check("deleted conversation returns 404 on GET", resp_get_after.status_code == 404)
    resp_del_after = client.delete(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
    check("deleting again returns 404", resp_del_after.status_code == 404)
except Exception as e:
    check("conversations management", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED")
else:
    failed = [label for label, ok in results if not ok]
    print("FAILED:\n  " + "\n  ".join(failed))
    sys.exit(1)
