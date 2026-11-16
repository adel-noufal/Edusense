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

def get_auth_headers(email: str, role: str):
    token = create_access_token(subject=email, role=role)
    return {"Authorization": f"Bearer {token}"}


def test_task8_chatbot_overhaul():
    results.clear()
    client = TestClient(app)
    db = SessionLocal()
    try:
        test_user = db.query(User).first()
        if not test_user:
            test_user = User(email="test_chatbot_user@edusense.com", password_hash="hash", name="Chatbot Tester", role="instructor")
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
        user_email = test_user.email
        user_role = test_user.role
    finally:
        db.close()

    headers = get_auth_headers(user_email, user_role)

    print("\n--- Test 1: Chatbot Config & Dedicated / Third Key Support ---")
    s = Settings(
        chatbot_name="EduMentor",
        chatbot_persona="You are a patient CS tutor.",
        gemini_api_key="primary-key-1,secondary-key-2",
        chatbot_gemini_api_key="dedicated-chatbot-key-12345",
    )
    check("chatbot_name configurable", s.chatbot_name == "EduMentor")
    check("chatbot_persona configurable", "patient CS tutor" in s.chatbot_persona)
    check("chatbot_gemini_api_key configurable", s.chatbot_gemini_api_key == "dedicated-chatbot-key-12345")
    check("gemini_api_keys includes dedicated chatbot key", "dedicated-chatbot-key-12345" in s.gemini_api_keys)
    check("gemini_api_keys has at least 3 keys when configured", len(s.gemini_api_keys) == 3, f"got {s.gemini_api_keys}")

    print("\n--- Test 2: GET /api/ai/chat/settings ---")
    resp = client.get("/api/ai/chat/settings", headers=headers)
    check("status 200", resp.status_code == 200, f"got {resp.status_code}")
    data = resp.json() if resp.status_code == 200 else {}
    check("chatbot_name present in response", "chatbot_name" in data and bool(data["chatbot_name"]))
    check("persona_preview present in response", "persona_preview" in data and bool(data["persona_preview"]))

    print("\n--- Test 3: POST /api/ai/chat/upload ---")
    fake_txt = io.BytesIO(b"Artificial Intelligence in education enables adaptive learning.")
    resp = client.post(
        "/api/ai/chat/upload",
        files={"file": ("test_notes.txt", fake_txt, "text/plain")},
        headers=headers,
    )
    check("valid text upload status 200", resp.status_code == 200, f"got {resp.status_code}")
    data = resp.json() if resp.status_code == 200 else {}
    check("filename matches", data.get("filename") == "test_notes.txt")
    check("char_count matches", data.get("char_count") == len("Artificial Intelligence in education enables adaptive learning."))
    check("text extracted correctly", "Artificial Intelligence" in (data.get("text") or data.get("extracted_text") or ""))

    empty_file = io.BytesIO(b"")
    resp_empty = client.post(
        "/api/ai/chat/upload",
        files={"file": ("empty.txt", empty_file, "text/plain")},
        headers=headers,
    )
    check("empty file raises 422", resp_empty.status_code == 422, f"got {resp_empty.status_code}")

    print("\n--- Tests 4 & 5: POST /api/ai/chat Conversation & Context Injection ---")
    test_conv_id = f"test-conv-{uuid.uuid4().hex[:8]}"
    mock_orchestrator_result = OrchestratorResult(
        answer="Sure, binary search operates in O(log n) time.",
        sources=["cs_algorithms.pdf"],
        web_sources=[],
        mode="online_rag_only",
        rag_chunks_used=1,
        web_results_used=0,
        unverified=False,
    )

    with patch("app.api.ai.orchestrator._run_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_orchestrator_result

        resp = client.post(
            "/api/ai/chat",
            json={
                "message": "What is the time complexity of binary search?",
                "conversation_id": test_conv_id,
            },
            headers=headers,
        )
        check("chat status 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json() if resp.status_code == 200 else {}
        check("returns conversation_id", data.get("conversation_id") == test_conv_id)
        check("returns answer", "O(log n)" in data.get("answer", ""))
        check("returns chatbot_name", bool(data.get("chatbot_name")))

        called_prompt = mock_exec.call_args.kwargs.get("query") or mock_exec.call_args[0][0]
        check("system persona injected into query", "[System:" in called_prompt)

        mock_orchestrator_result_2 = OrchestratorResult(
            answer="Based on your uploaded notes, adaptive learning personalizes content.",
            sources=[],
            web_sources=[],
            mode="general",
            rag_chunks_used=0,
            web_results_used=0,
            unverified=False,
        )
        mock_exec.return_value = mock_orchestrator_result_2

        resp2 = client.post(
            "/api/ai/chat",
            json={
                "message": "Summarize my notes.",
                "conversation_id": test_conv_id,
                "file_context": "Chapter 1: Adaptive Learning adjusts pace based on student answers.",
            },
            headers=headers,
        )
        check("follow-up status 200", resp2.status_code == 200, f"got {resp2.status_code}")
        check("conversation_id preserved", resp2.json().get("conversation_id") == test_conv_id)
        called_prompt_2 = mock_exec.call_args.kwargs.get("query") or mock_exec.call_args[0][0]
        check("file_context injected into query", "[Uploaded file context]" in called_prompt_2)
        check("user question included in query", "Summarize my notes." in called_prompt_2)

    db = SessionLocal()
    try:
        messages = (
            db.query(ChatMessageModel)
            .filter_by(conversation_id=test_conv_id)
            .order_by(ChatMessageModel.created_at.asc())
            .all()
        )
        check("messages persisted in database", len(messages) == 4, f"got {len(messages)} messages")
        if len(messages) >= 2:
            check("first message is user", messages[0].role == "user")
            check("second message is assistant", messages[1].role == "assistant")
    finally:
        db.close()

    print("\n--- Tests 6, 7 & 8: Conversations Management (List, Get, Delete) ---")
    try:
        resp_list = client.get("/api/ai/chat/conversations", headers=headers)
        check("list conversations status 200", resp_list.status_code == 200, f"got {resp_list.status_code}")
        convs = resp_list.json() if resp_list.status_code == 200 else []
        check("conversations is list", isinstance(convs, list))
        matching_conv = next((c for c in convs if c.get("conversation_id") == test_conv_id), None)
        check("created conversation in list", matching_conv is not None)
        if matching_conv:
            check("message_count is 4", matching_conv.get("message_count") == 4, f"got {matching_conv.get('message_count')}")
            check("preview contains user query", "binary search" in matching_conv.get("preview", ""))

        resp_get = client.get(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
        check("get conversation status 200", resp_get.status_code == 200, f"got {resp_get.status_code}")
        conv_detail = resp_get.json() if resp_get.status_code == 200 else {}
        check("get conversation messages count is 4", len(conv_detail.get("messages", [])) == 4)
        history = conv_detail.get("messages", [])
        check(
            "conversation history includes both user and assistant turns",
            [message.get("role") for message in history] == ["user", "assistant", "user", "assistant"],
        )
        check(
            "conversation history includes both user prompts",
            "binary search" in history[0].get("content", "").lower()
            and "summarize my notes" in history[2].get("content", "").lower(),
        )
        print("GET conversation response:", __import__("json").dumps(conv_detail, ensure_ascii=False))

        resp_del = client.delete(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
        check("delete conversation status 200", resp_del.status_code == 200, f"got {resp_del.status_code}")
        check("deleted count returned", resp_del.json().get("deleted") == 4)

        resp_get_after = client.get(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
        check("deleted conversation returns 404 on GET", resp_get_after.status_code == 404)
        resp_del_after = client.delete(f"/api/ai/chat/conversations/{test_conv_id}", headers=headers)
        check("deleting again returns 404", resp_del_after.status_code == 404)
    except Exception as e:
        check("conversations management", False, str(e))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    assert passed == total, f"FAILED: {[label for label, ok in results if not ok]}"


if __name__ == "__main__":
    test_task8_chatbot_overhaul()
