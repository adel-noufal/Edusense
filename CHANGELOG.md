# Changelog

All notable changes to **EduSense** are documented here.

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
