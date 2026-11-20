# Changelog

All notable changes to **EduSense** are documented here.

---

## [Unreleased] — Reliability & Hardening Batch (9 work items)

### Infrastructure — Central Gemini client with key × model rotation
- `app/services/gemini.py` is now the single Gemini client used by every agent; duplicated direct calls removed.
- Rotates over `(API key × model)` pairs: keys round-robin, then the next model in an ordered per-task chain (`EDUSENSE_GEMINI_MODELS`, `_MODELS_CHAT`, `_MODELS_SCRIPT`).
- Cooldown with `retry-after` / exponential backoff + jitter on 429/503/timeout/model-not-found; 400 and safety blocks surface immediately.
- Typed `GeminiError` codes (`QUOTA_EXHAUSTED`, `MODEL_UNAVAILABLE`, `SAFETY_BLOCKED`, `TIMEOUT`, `INVALID_RESPONSE`); masked-key logging; `GET /api/ai/gemini-health` diagnostic endpoint.
- Fixed rotator deadlock (lock held across yield) and per-key model fallback for keys whose projects can't serve a given model.

### 1. Video generation — length control, dedupe, structured errors
- Duration → target word count via configurable `EDUSENSE_VIDEO_NARRATION_WPM` (default 140) with ±`EDUSENSE_VIDEO_SCRIPT_TOLERANCE` (10%) enforcement, corrective expand/condense passes, and hard failure instead of wrong-length scripts.
- Outline-first generation with per-section context; n-gram duplicate detection rejects repeated sections.
- Scene duration driven by real TTS audio length; per-scene TTS timeouts (`EDUSENSE_VIDEO_TTS_TIMEOUT`).
- Video jobs return structured errors `{code, stage, message}` (`script_generation`/`tts`/`render`) surfaced in the UI with retry.

### 2. Reports — minimum data, duration cap, CSV export
- New `app/services/report_data.py`: shared sufficiency assessment (`REPORT_MIN_EMOTION_SAMPLES`, `REPORT_MIN_ATTENDED_MINUTES`, `REPORT_MIN_PARTICIPANTS`) — below threshold the report shows an explicit "Not enough data yet" state instead of fabricated numbers.
- Attended duration clamped to `REPORT_MAX_ATTENDED_MINUTES` (default 720) and flagged `duration_capped`; scheduled vs attended duration are now distinct everywhere.
- `GET /api/reports/.../export.csv` — UTF-8 BOM, escaped fields, per-session summary + per-interval emotion timeline; Arabic opens correctly in Excel.

### 3. Recommendations grounded in real data
- `recommendation_agent.py` computes metrics deterministically (emotion distribution, engagement, quiz performance, attendance) and passes only those facts to the LLM as structured JSON; output validated against a schema and filler rejected.
- Each recommendation cites its evidence; insufficient data → no recommendations, only the empty state. Generic fallback filler removed.

### 4. Accent Palette removed
- Setting, state, CSS-variable switching, and persisted preference code removed from Profile (instructor + student); theme locked to default Teal. Language, animated background, email notifications, and compact view unchanged; legacy localStorage keys cleaned.

### 5. Emotion Recognition Trial — larger camera area
- Camera stage enlarged to ~50vh with `object-fit: contain`, mirrored selfie view, emotion-colored confidence overlay, face/no-face and permission-denied states; stream stops on unmount; "analyzed once per second, not stored" unchanged.

### 6. Student Exams hardened
- `Quiz.reveal_answers` added; correct answers/explanations stripped from student payloads when disabled.
- Question count enforced server-side (pad/truncate), difficulty normalized to Easy/Medium/Hard, `type` inferred for generated questions.
- Exam guards: one-attempt enforcement, unpublished/past-due exams blocked (403), resubmission replay blocked (400).
- Grading resolves answer letters, numeric indexes, option text, true/false, and short-answer; server-side timing validated; duplicate "Submitted" badge removed.

### 7. Session duration optional / unbounded
- `sessions.duration` nullable — `NULL` = "No time limit" (default in UI); positive values only, no upper bound. Migration `a1b2c3d4e5f6` (reversible).
- Create/edit UI (Sessions + Dashboard) with "No time limit" checkbox; status treats NULL as unbounded "ongoing"; reports clamp via item 2.

### 8. Knowledge Base persistent chat history
- KB conversations stored in `chat_messages` under `kb:`-prefixed IDs, user-scoped; endpoints: list (with search), get, rename (PATCH), delete.
- Auto title from first message, bounded 12-message history window sent to the RAG prompt, source citations persisted on assistant messages; instructor-only (students get 403).
- `KnowledgeBase.jsx` QA panel has a conversation sidebar, new/rename/delete/search, and resume with full context.

### 9. AI Chatbot output quality
- System prompt rewritten: EduSense teaching-assistant role, answers in the user's language (EN/AR/mixed), concise structured output, honest "I don't know", no fabricated citations, no prompt leakage.
- New safe Markdown renderer (`frontend/src/utils/markdown.jsx`): headings, lists, bold/italic, inline code, fenced code blocks with copy button, `$...$` math, safe links — no `dangerouslySetInnerHTML`.
- Regenerate button on the last assistant reply; Stop button aborts in-flight requests; typed error messages; generation tuned (chat task chain, temperature 0.4, 2048 max tokens).

### Tests
- `test_task_video_script_quality.py` — word-count targets, corrective pass, n-gram dedupe.
- `test_task_reports_items2_3.py` — thresholds, duration clamp, insufficient-data state, CSV, recommendation grounding.
- `test_task_exam_hardening.py` — normalization, one-attempt, publish/due guards, answer stripping.
- `test_task_items7_8.py` — optional duration validation/status + KB history CRUD and user isolation (30 checks).
- Gemini rotation tests updated for key × model semantics; `GET /api/ai/gemini-health` diagnostic added.

---

## [2.1.0] — 2026-10-24 (branch: feature/sessions-ingestion)

### Added — Task 1: Vector Store Foundation
- Persistent ChromaDB vector store with cosine distance (`sentence-transformers/all-MiniLM-L6-v2` embeddings, ONNX fallback)
- `RAG_Search_Tool` with metadata filtering (subject, grade_level) and configurable min_score threshold
- Idempotent ingestion via `delete_by_source` before insert
- Collection persistence to local disk (`data/chroma/chroma.sqlite3`)

### Added — Task 2: Dual Ingestion Pipeline
- **General curriculum ingestion** (`POST /api/rag/ingest`): token-based splitting (langchain/tiktoken, 500–1000 tokens, configurable overlap)
- **Session resource auto-ingestion**: character-based splitting (1000 chars, 200 overlap) triggered on instructor file upload (`/instructor/sources`)
- Both paths share the same Chroma collection but use different chunking strategies

### Added — Task 3: RAG Search Tool Verification
- Semantic similarity search with ranking and metadata filtering
- Default threshold `RAG_MIN_SCORE=0.6` enforced in tool and API
- Subject + grade_level filters verified against test corpus

### Added — Task 4: RAG Grounding + Verification Badges
- `AgentResult` dataclass extended with `unverified: bool` field
- Lesson/Quiz/Flashcard agents return `sources: List[str]` and `unverified: bool`
- Template fallback path marks `unverified=True`, `sources=[]`
- Frontend `AITools.jsx` renders 🛡️ Verified / ⚠️ Unverified badges in result headers
- Test coverage: 7/7 tests passing (RAG match → verified; no match → unverified)

### Added — Task 5: Agentic Chatbot + Orchestrator
- `Web_Search_Tool` via Tavily API (configurable `tavily_api_key`)
- `AgentOrchestrator` with 4 failover states:
  1. `online_rag_web_llm` — RAG + Web + LLM (Gemini)
  2. `online_rag_only` — RAG only (web failed/empty)
  3. `offline_rag_template` — RAG + local template (LLM unavailable)
  4. `offline_template_only` — template only (RAG + LLM unavailable)
- Per-tool timeouts: RAG 2s, Web 5s (ThreadPoolExecutor + asyncio.wait_for)
- `/api/ai/chat` endpoint with token-bucket rate limiting (30 req/min/user)
- `ChatMessage` SQLAlchemy model with `conversation_id` for persisted history
- Streaming endpoint `/api/ai/chat/stream` (SSE)
- Frontend `ChatbotGenerator` component with conversation sidebar, dark mode, markdown rendering

### Changed
- `backend/app/agents/orchestrator.py` rewritten with async tool timeouts
- `backend/app/api/ai.py` updated with rate limiting and conversation persistence
- `backend/app/models/models.py` added `ChatMessage` model
- `frontend/src/pages/AITools.jsx` added `ChatbotGenerator` tab and badges
- `frontend/src/components/Layout.jsx` added "AI Chatbot" nav item for instructors
- `frontend/src/main.jsx` added lazy-loaded route `/instructor/chatbot`

---

## [2.0.0] — 2026-08-06

### Added
- 🎴 **Flashcard Generation Agent** — 6th AI agent producing study card decks via Gemini / Ollama
- ⚡ **4-Model Offline Task Router** — Task-specific Ollama model assignment (qwen2.5, mistral, llama3.1, llama3.2)
- 🌐 **Intelligent Auto-Failover** — Gemini 2.0 Flash → Ollama → Local Templates (zero crashes)
- 📧 **APScheduler Email Reminders** — Automated Gmail SMTP session reminders (15→1 min countdown)
- 🎭 **PyTorch v7 EfficientNet-B0** — Custom-trained emotion model (90.9% accuracy, 7 classes)
- 🐳 **Docker Compose Setup** — `docker-compose.yml` for PostgreSQL + backend
- 🚀 **Windows Batch Scripts** — `start-backend.bat`, `start-frontend.bat`, `install-local.bat`
- 📊 **OpenAPI Swagger UI** — Rich interactive API documentation at `/docs`
- 🏗️ **GitHub Actions CI/CD** — Automated backend Python compile + frontend Vite build checks
- 📜 **MIT License** — Open source licensing
- 📋 **CONTRIBUTING.md** — Contribution guidelines for collaborators
- 📄 **CHANGELOG.md** — Project version history

### Changed
- Updated FastAPI version metadata to `2.0.0`
- Enhanced OpenAPI metadata with LinkedIn contact, license info, and API tag descriptions
- Updated all documentation to include LinkedIn author profile
- Improved `README.md` with Instructor & Student Workflow Mermaid diagrams
- Updated `docs/ARCHITECTURE.md` with AI Router flowchart diagrams and SMTP sequence diagrams
- Fixed `IndentationError` bugs in `flashcard_agent.py`, `lesson_agent.py`, `quiz_agent.py`

---

## [1.0.0] — 2026-06-30

### Added
- Initial release: FastAPI backend + React 18 + Vite frontend
- JWT authentication (instructor / student / admin roles)
- 6 core AI agents: Emotion, Engagement, Recommendation, Lesson, Quiz, Report
- DeepFace emotion detection fallback
- ReportLab PDF report export
- SQLAlchemy ORM (SQLite / PostgreSQL)
