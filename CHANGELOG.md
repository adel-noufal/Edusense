# Changelog

All notable changes to **EduSense** are documented here.

---

## [2.1.2] — 2026-11-22 — LLM load spread, KB/Chatbot separation, login

### Fixed — the LLM layer collapsed on the first request
- A 404/410 from a provider no longer disables a model "permanently for the process".
  It is disabled for 6 hours (`LLMRouter.MODEL_DISABLE_TTL`) and then re-verified
  against the provider's live `/models` list, which `candidates()` now consults
  (cached 10 minutes) instead of trusting the hardcoded catalog.
- Gemini is the last cloud option for every short feature (`kb_chat`, `prompt_enhance`,
  `flashcards`, `quizzes`, `exams`, `general`) and stays primary only for long-context
  work (`video_script`, `reports`).
- Ollama is appended as the guaranteed last resort for every feature, is re-detected
  lazily when the daemon starts late, and is never disabled by a 404. Local models are
  ordered fast-first (`llama3.2` before the 70B-class models) so a CPU-only machine can
  actually answer.
- Circuit breaker: one request tries at most 4 cloud/local pairs (plus any local
  fallback) instead of walking every cooled-down pair; failures return a short readable
  message and never the provider's raw JSON.
- Prompt-enhance and RAG answers are cached (1 hour), so repeat clicks spend no quota.
- `/api/admin/llm-status` now exposes per-model `disabled_until` and `disable_reason`,
  plus Ollama reachability; `/api/ai/available-models` always returns the four local
  models when Ollama is up and an actionable `ollama_hint` when it is down.
- `LocalLLM.generate()` routes through the multi-provider router instead of calling
  Gemini first for every agent.

### Changed — Knowledge Base chat and AI Chatbot are separate products
- AI Chatbot conversations use the `web:` prefix and are stored/listed separately from
  `kb:` conversations; a reversible startup migration tags legacy conversations
  (6 rows tagged on the first boot after this change).
- The chatbot never retrieves from the Knowledge Base; it uses web search + general
  knowledge + a file attached to that conversation only. The "No files / Selected files /
  All files" modes were removed from the chatbot page.
- Knowledge Base chat gains an engine selector (Auto / Private / Cloud) with a privacy
  badge; `POST /api/rag/ask` accepts `engine`, and `/api/rag/engine` advertises the modes.
- Knowledge Base answers are page-aware: "page 40" or "pages 40-45" filters to those
  pages and one neighbour on each side, pulling the pages directly when similarity
  search lands elsewhere.

### Fixed — login and public pages
- The 6-character minimum and its hint apply to registration only; the login form shows
  neither.
- `SECRET_KEY` / `EDUSENSE_SECRET_KEY` are now honoured by settings, so a restart keeps
  existing JWTs valid.
- A 401 clears the stored session and redirects to `/login` with "Your session expired."
- The mojibake scan also covers untracked files and the built `frontend/dist` bundle.

### Fixed — small UI issues
- Background-job polling treats the reaper's `failed` status as terminal and drops
  stored jobs the server no longer knows about, so the sidebar stops counting a dead job.
- AI messages show the provider/model that answered instead of an empty icon row.

---

## [2.1.1] — 2026-11-22 — Encoding, Knowledge Base and video-integrity hotfix

### Fixed — UTF-8 corruption (mojibake)
- Eight non-English strings were double-encoded (UTF-8 read as Windows-1252 and re-saved as
  UTF-8) in commit `81c23f2`, which rewrote line endings across the tree. The language toggle
  showed `Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©` instead of `العربية`, arrows rendered as `â–¼`, and the README was unreadable.
- All affected files were repaired by reversing the double encoding line-by-line; the i18n
  dictionary is now byte-identical to the last good commit (`00f78f0`) for the affected lines.
- Added `.editorconfig`, `.gitattributes`, `scripts/mojibake.py`, `scripts/mojibake_scan.py`,
  `scripts/fix_mojibake.py`; the scan runs in `verify.bat` and in CI.

### Fixed — Knowledge Base empty / "cannot reach backend"
- Root cause: `sentence-transformers` could not import because the venv's `jinja2/_identifier.py`
  was itself mojibake-corrupted (`re.PatternError: bad character range €-Í`).
  `vector_store.get_embedding_function()` then silently fell back to Chroma's ONNX MiniLM and
  `init_collection()` raised `Embedding function conflict: new: onnx_mini_lm_l6_v2 vs persisted:
  sentence_transformer`, which surfaced as HTTP 500 and "0 documents".
- `jinja2` was reinstalled; the four documents are listed again with their original chunk
  counts (129 / 15 / 1 / 1), collection total 146 chunks.
- `get_embedding_function()` no longer falls back silently; `init_collection()` opens an
  existing collection with its persisted embedding function and raises a readable conflict
  error. The fallback is opt-in via `EDUSENSE_ALLOW_ONNX_EMBEDDING=1`.
- Knowledge Base UI now reports HTTP status plus server detail for HTTP errors, and names the
  real API base URL for network failures.

### Fixed — video jobs reported "completed" without files
- `services/binaries.py` resolves `ffmpeg`/`ffprobe` through `EDUSENSE_FFMPEG_PATH`, `PATH`,
  WinGet `Links`, WinGet package folders and common install paths; the video service and doctor
  both use it.
- New `validate_video_artifacts()`: a job is only `completed` when the MP4 exists, ffprobe
  reports a positive duration and `narration.mp3` is present; otherwise the job fails with a
  readable reason.
- The MP4 is now included in the ZIP download; the player shows an inline `<video>` and a
  Download MP4 button whenever the file exists.
- Session material is excerpted by topic relevance instead of dumping the first pages of the
  attached PDF, and retrieved excerpts no longer appear in the visible Notes field.

### Fixed — models hidden from the dropdown
- `llm_config.json` contained a duplicate `nvidia` key; the second block (all
  `free_tier: false`) silently overrode the correct one. Removed, NVIDIA models are now offered
  with a `Free - rate limited` badge.
- Groq and OpenRouter `:free` models are marked as free-with-limits instead of hidden.
  `ALLOW_PAID_MODELS=false` still hides every paid model.
- `available-models` returns badge/task/speed metadata for the UI.

### Fixed — exports and gate
- Flashcard CSV exports use `utf-8-sig` so Arabic opens correctly in Excel.
- `doctor` now imports `app.main` and verifies the persisted embedding model loads.
- `verify.bat` adds the mojibake scan and `pytest --collect-only`; `.github/workflows/ci.yml`
  runs the encoding gate, an import smoke test, `pytest -m "not live_provider"` and the
  frontend build without real keys.

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
