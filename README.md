# ðŸŽ“ EduSense â€” Multi-Agent AI Education Platform

[![Author](https://img.shields.io/badge/Author-Adel_Mohamed_Noufal-blue.svg)](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Adel_Mohamed_Noufal-0A66C2.svg?logo=linkedin)](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
[![Emotion Model](https://img.shields.io/badge/PyTorch-v7_EfficientNet--B0_(90.9%25)-EE4C2C.svg?logo=pytorch)](https://github.com/adel-noufal/Edusense)
[![AI Backend](https://img.shields.io/badge/AI_Providers-Gemini_2.0_%7C_Ollama-4285F4.svg)](https://github.com/adel-noufal/Edusense)
[![Stack](https://img.shields.io/badge/Stack-React_18_%7C_FastAPI_%7C_PostgreSQL-00599C.svg)](https://github.com/adel-noufal/Edusense)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.1.0-blueviolet.svg)](CHANGELOG.md)
[![CI/CD](https://github.com/adel-noufal/Edusense/actions/workflows/ci.yml/badge.svg)](https://github.com/adel-noufal/Edusense/actions)

> **EduSense** is a fully local, multi-agent AI Education Platform designed for adaptive learning, automated assessment & lesson authoring, real-time webcam emotion telemetry, grounded multi-source RAG, interactive video generation, and proctored student evaluations.
>
> ðŸ‘¤ **Author:** [Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
> ðŸ”— **LinkedIn:** [https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
> ðŸ”— **GitHub Repository:** [https://github.com/adel-noufal/Edusense](https://github.com/adel-noufal/Edusense)

## Addendum 7 Quality & Verification

- Run the full local verification gate with `verify.bat`.
- External-provider tests are marked `live_provider` and are skipped unless `RUN_LIVE_PROVIDERS=1`.
- Real-time quality gates cover teaching-style differences, duration removal from non-video tools, markdown-free structured output, and PPTX visual lint.
- Ollama remains the offline tier for prompt enhancement and local AI generation.

---

## ðŸŒŸ Key Features & AI Architecture

EduSense features **8 specialized AI agents**. Agents 1â€“7 are coordinated sequentially by `EduSenseAgentWorkflow` ([`backend/app/agents/workflow.py`](backend/app/agents/workflow.py)) for post-session analytics and pedagogical improvement, while Agent 8 (RAG Knowledge Base & Chatbot) is driven on demand through a dedicated multi-source orchestrator ([`backend/app/agents/orchestrator.py`](backend/app/agents/orchestrator.py)):

1. ðŸŽ­ **Emotion Analysis Agent** â€” Analyzes webcam frames in real-time using a custom **v7 PyTorch EfficientNet-B0** model (**90.9% Accuracy**) with DeepFace fallback.
2. ðŸ“Š **Student Engagement Agent** â€” Computes real-time engagement and attention metrics from emotion distributions.
3. ðŸ’¡ **Recommendation Agent** â€” Generates pedagogical interventions when engagement drops below threshold (< 62%).
4. ðŸ“š **Lesson Generation Agent** â€” Generates structured lessons, slides, outlines, and teaching scripts grounded in curriculum RAG and web search fallback.
5. ðŸ“ **Quiz & Exam Agent** â€” Generates adaptive MCQs, True/False, and short-answer questions (RAG & Web grounded) or supports full manual authoring, with instructor-configurable timers, anti-cheat lockdown, and direct deployment to student Exams/Assignments.
6. ðŸŽ´ **Flashcard Generation Agent** â€” Produces high-yield, pedagogically distinct study card decks across 20 distinct cognitive dimensions grounded in uploaded materials and recent web context.
7. ðŸ“„ **Report Generation Agent** â€” Generates executive PDF reports via `ReportLab` with actual attended-duration analytics.
8. ðŸ§  **RAG Knowledge Base & AI Chat Assistant** â€” Grounded PDF/DOCX/PPTX course material retrieval via ChromaDB vector embeddings (100MB+ support), customizable persona Chatbot (`POST /api/ai/chat`), grounded file upload (`POST /api/ai/chat/upload`), persistent conversation history, and Knowledge Base Admin Dashboard (`/instructor/knowledge-base`).

---

## ðŸ—ºï¸ Roadmap & Implemented Capabilities

- âœ… **Asynchronous Task Lifecycle & Dashboard Optimization**: DONE â€” non-blocking background analytics generation jobs (`GenerationJobContext`), tab-switch resilience, and bidirectional session content linking (lessons + quizzes) with one-click unlink support.
- âœ… **Accurate Attended-Duration Tracking**: DONE â€” separate tracked student attended duration (`joined_at`, `left_at`) from scheduled session duration; accurate attendance minutes and percentages calculated across all instructor reports.
- âœ… **High-Capacity Knowledge Base / RAG**: DONE â€” 100MB+ file upload support via chunked streaming, file format validation using magic bytes (PDF, DOCX, PPTX, TXT, MD), non-blocking background ingestion with status polling, and live document preview.
- âœ… **Crash-Resistant AI Lessons Tab**: DONE â€” hardened state handling, topic extraction fallbacks, and seamless rendering across online and offline failover tiers.
- âœ… **Dual-Mode Quiz Authoring & Exam Deployment**: DONE â€” full manual quiz/exam authoring alongside AI generation, dynamic exam settings editor (timers, fullscreen, webcam proctoring, pass percentage, back-navigation locking), and toggles for showing/hiding correct answers.
- âœ… **Pedagogically Distinct Flashcards**: DONE â€” eliminated repetitive card generation using a 20-dimensional pedagogical framework (definitions, mechanisms, contrasts, edge cases, mnemonics) grounded in RAG curriculum or Tavily web results.
- âœ… **Educational Video Studio & Scene Editor**: DONE â€” per-scene narration audio synthesis using gTTS (with tone fallback), duration-synced slide transitions, interactive player with autoplay/scrubbing, and an in-UI scene editor (`PUT /api/videos/{id}/scenes`) supporting re-rendering.
- âœ… **Customizable AI Chatbot with Grounded Uploads & History**: DONE â€” configurable bot identity (`chatbot_name`, `chatbot_persona`), dedicated 3rd API key support (`EDUSENSE_CHATBOT_GEMINI_API_KEY`), file context injection (`POST /api/ai/chat/upload`), and persistent sidebar conversation history.
- âœ… **Student Assessment Hub (Exams & Assignments)**: DONE â€” fixed student authentication token reactivity in `AuthContext`, resolved infinite loaders, populated course `session_title` on all exam/assignment cards, and added deadline-aware submission portals.
- âœ… **Hardening, Schema Alignments & Robust Key Rotation**: DONE â€” aligned Alembic migrations with `seed.py` for SQLite/PostgreSQL, eliminated timer race conditions and attempt resumption discrepancies in `Quiz.jsx`, and expanded Gemini key rotation to fail over on revoked/suspended keys (400/403 `API_KEY_INVALID`, 503) as well as 429 rate limits.
- âœ… **Privacy & Consent Engine**: DONE â€” granular webcam consent tracked separately per purpose (`emotion_detection` vs. `quiz_anti_cheat`), enforced server-side, with non-blocking platform fallback and draft policy documentation (`docs/PRIVACY_POLICY.md` and `docs/TERMS_OF_SERVICE.md`).

---

## ðŸ‘¨â€ðŸ« Instructor System Workflow

```mermaid
sequenceDiagram
  autonumber
  actor I as Instructor
  participant UI as React Frontend
  participant API as FastAPI Backend
  participant WF as Multi-Agent Workflow
  participant PDF as ReportLab Service

  I->>UI: 1. Create Class Session & Upload 100MB+ Course Materials
  UI->>API: POST /api/sessions & POST /api/sessions/{id}/resources
  API->>UI: Session Created & PDF/DOCX Ingested into ChromaDB RAG
  I->>UI: 2. Launch Live Classroom & View Telemetry
  UI->>API: GET /api/sessions/{id}/emotions/distribution (Polling)
  API->>UI: Real-time Emotion % & Engagement Timeline
  UI->>I: Displays Engagement Alert (if < 62%)
  I->>UI: 3. Author Assessment (AI Generated or Manual Mode)
  UI->>API: POST /api/ai/quiz (Configured with Anti-Cheat & Timers)
  API->>WF: RAG-first -> Web Fallback -> Gemini/Ollama
  WF-->>UI: Draft Assessment Ready for Review & Answer Toggle
  I->>UI: 4. Link & Publish as Proctored Exam or Assignment
  UI->>API: POST /api/quizzes/{id}/publish (Mode: exam / assignment)
  API-->>UI: Deployed to Student Assessment Hub with Course Title
  I->>UI: 5. Generate Accurate Analytics & Export Report
  UI->>API: POST /api/reports/{session_id}/generate
  API->>PDF: Calculate Attended Minutes (joined_at / left_at)
  PDF-->>UI: Download Link for Executive PDF Report
```

---

## ðŸŽ“ Student System Workflow

```mermaid
sequenceDiagram
  autonumber
  actor S as Student
  participant UI as React Frontend
  participant Cam as Webcam Processor
  participant API as FastAPI Backend
  participant ML as PyTorch EfficientNet-B0 v7

  S->>UI: 1. Browse Sessions & One-Click Register
  UI->>API: POST /api/sessions/{id}/register
  API-->>UI: Registered (Shows Countdown & Active Join Button)
  S->>UI: 2. Enter Live Classroom
  UI->>Cam: Initialize Webcam Stream (with Granular Consent)
  loop Every N seconds
    Cam->>UI: Capture Frame (Base64 JPEG)
    UI->>API: POST /api/sessions/{id}/emotions
    API->>ML: Classify Emotion (v7 EfficientNet-B0)
    ML-->>API: Emotion (Happy, Neutral, Confused, Sad, etc.) + Confidence
    API-->>UI: Emotion Log Saved & Attendance Timestamps Recorded
  end
  S->>UI: 3. Access Student Assessment Hub
  alt Take Proctored Exam
    S->>UI: Open /student/exams (View Course Title & Deadline)
    UI->>UI: Enforce Fullscreen Lockdown, Anti-Cheat & Strict Timers
    UI->>API: POST /api/quizzes/{id}/submit
  else Complete Homework Assignment
    S->>UI: Open /student/assignments & Submit Document/Answers
    UI->>API: POST /api/assignments/{id}/submit
  end
  API-->>UI: Instant Score, Breakdown & Instructor Feedback
  S->>UI: 4. Study with Grounded AI Chatbot & Flashcards
  UI->>API: POST /api/ai/chat (with File Context & Saved History)
  API-->>UI: Pedagogical Response with Source Citations
```

---

## ðŸŽ¯ Student Assessment Hub: Exams & Assignments

EduSense provides dedicated, authenticated student portals designed to eliminate infinite loaders and display full course context:

### 1. Proctored Exams (`/student/exams`)
- **Direct Course Linking**: Displays the enrolled course name (`session_title`) alongside exam title, duration, question count, and pass threshold.
- **Anti-Cheat Enforcement**:
  - Fullscreen lockdown mode with active detection of tab switching, window blurring, and fullscreen escape attempts.
  - Dynamic user-traceable watermark overlay across the screen.
  - Optional AI-assisted proctoring via webcam for violation detection.
- **Resilient Timers**: Per-quiz and per-question timers with server-side start-time reconciliation on refresh or resumption to eliminate time-drift exploits.
- **Submission & Results**: Immediate scoring for objective questions and violation auditing for instructor review.

### 2. Homework & Assignments (`/student/assignments`)
- **Course-Grouped Views**: Lists assignments grouped by session title with due dates, point values, and submission statuses.
- **Submission Workflow**: Supports multi-format file uploads (PDF, DOCX, code files) and text submissions.
- **Feedback & Grading**: Displays graded results, rubric breakdowns, and instructor feedback remarks.

---

## ðŸŽ¬ Educational Video Studio & Scene Editor

EduSense features an end-to-end automated educational video synthesis engine:

1. **Structured Script & Scene Generation**: Outlines instructional slides with headings, visual cues, bullet points, and narration scripts.
2. **Audio Narration Pipeline**: Synthesizes speech per scene using `gTTS` (with sinusoidal tone fallback) and measures exact audio duration in seconds.
3. **Synchronized HTML5 Player**: Generates a self-contained, responsive `player.html` with timed slide autoplay, audio playback, progress scrub bar, and play/pause controls.
4. **In-UI Scene Editor**: Instructors can modify scene titles, narration text, and display duration directly in the frontend (`/instructor/ai-tools` Video Tab) and trigger instant re-rendering via `PUT /api/videos/{id}/scenes`.

---

## ðŸ¤– Customizable AI Chatbot with Grounded File Upload

The AI Chatbot (`/instructor/ai-tools` AI Chatbot Tab) provides an interactive teaching assistant:

- **Custom Identity & Persona**: Instructors can customize the chatbot name (e.g., `EduSense Mentor`) and behavioral persona via environment settings or API.
- **Dedicated 3rd API Key**: Supports `EDUSENSE_CHATBOT_GEMINI_API_KEY` to protect primary lesson/quiz generation quota from chat traffic.
- **File Upload & Grounding**: Students and instructors can upload reference documents (`.pdf`, `.txt`, `.docx`) directly into the chat session (`POST /api/ai/chat/upload`) to ground answers in specific files.
- **Persistent Conversation History**: All conversations are stored in the database (`chat_messages` table) with a collapsible sidebar for switching between past threads or deleting conversations.

---

## ðŸ§  Knowledge Base vs AI Chatbot â€” Two Different Tools

EduSense deliberately ships **two separate Q&A experiences** with different contracts:

| | **Knowledge Base** (`/instructor/knowledge-base` â†’ AI Chat Assistant) | **AI Chatbot** (`/instructor/ai-tools` â†’ AI Chatbot) |
|---|---|---|
| Grounding | **Strictly document-grounded (RAG-only)** | **General-purpose assistant** |
| No relevant document | Says plainly *"I couldn't find anything about that in the uploaded course materials"* and points to the Chatbot | Answers normally from model knowledge and/or live web search |
| File context | Scoped per document â€” each library card has an *"Ask a question about only this file"* button | Optional file attachment/context injection |
| Refusals | Refuses off-material questions honestly | Never refuses merely because no source is attached |

Both paths are protected by a user-facing answer sanitizer that strips any leaked internal prompt/guardrail text (`=== SCOPE GUARDRAIL ===`, `[System: ...]` scaffolding) before answers reach the UI â€” including template/offline fallbacks.

## ðŸ˜Š Emotion Recognition Trial (Student Dashboard)

The student dashboard home page includes a self-contained **Emotion Recognition Trial** widget (`frontend/src/components/EmotionTrial.jsx`):

- **Live Webcam mode** â€” analyzes the student's expression roughly once per second and shows the detected emotion + confidence.
- **Single Photo mode** â€” captures one frame and returns one analysis.
- Reuses the production detection pipeline via `POST /api/emotions/analyze-trial` (same v7 EfficientNet-B0 / DeepFace agent) â€” trial frames are **not** written to `emotion_logs` and no class session is required.
- Respects the existing consent engine: webcam access is gated behind the `emotion_detection` consent modal before the camera is opened.

---

## ðŸ”„ Open-Ended Multi-Provider, Multi-Key LLM Layer (Part A)

All AI features (video scripts, reports, recommendations, Knowledge Base chat, AI Chatbot, quizzes, flashcards, exams, question bank) route through **one central multi-provider router** â€” `backend/app/services/llm.py` (with transparent compatibility via `gemini.py`). Supports unlimited keys per provider, any number of providers, capability profiling, and best-fit routing.

### ðŸ”‘ Key Registry Naming Convention (Unlimited Keys & Hot-Add)
You can configure **any number of keys** across any number of providers in `backend/.env` without code changes.

1. **Pooled keys (comma-separated list)**:
   ```env
   <PROVIDER>_API_KEYS=key1,key2,key3
   # Examples:
   GROQ_API_KEYS=gsk_key1,gsk_key2
   NVIDIA_API_KEYS=nvapi-key1,nvapi-key2
   OPENROUTER_API_KEYS=sk-or-v1-key1,sk-or-v1-key2
   DEEPINFRA_API_KEYS=sk-di-key1
   CEREBRAS_API_KEYS=csk-key1
   ```
2. **Named & Feature-Dedicated keys**:
   ```env
   <PROVIDER>_KEY_<LABEL>=<key>
   # Examples:
   GEMINI_KEY_VIDEO_1=AIzaSy...       # Dedicated to video_script
   GROQ_KEY_CHAT=gsk_...              # Dedicated to kb_chat/chatbot
   NVIDIA_KEY_EXAM_PROD=nvapi-...     # Dedicated to quizzes/exams
   ```
3. **Full Backward Compatibility**:
   Existing Gemini variables remain fully detected and supported:
   ```env
   GEMINI_API_KEY=AIzaSy...
   EDUSENSE_GEMINI_API_KEY=AIzaSy...
   GEMINI_API_KEY_1=AIzaSy..., GEMINI_API_KEY_2=...
   CHATBOT_GEMINI_API_KEY=AIzaSy...   # Dedicated chatbot key
   ```
4. **Per-Key Metadata & Quota Groups**:
   Keys from the same Google Cloud project or provider account share quota. Set quota groups to cool down together on 429 rate limits:
   ```env
   <PROVIDER>_KEY_<LABEL>_GROUP=<project_or_account_name>
   <PROVIDER>_KEY_<LABEL>_FEATURE=<feature_name>
   <PROVIDER>_KEY_<LABEL>_PRIORITY=<1..100>
   # Legacy Gemini group mapping:
   GEMINI_KEY_GROUPS=0:projectA,1:projectB,2:projectB
   ```

### ðŸ§  Model Capability Profiles & Best-Fit Routing
Every model profile (`backend/app/core/llm_config.json`) defines verified specs: context window, max output tokens, latency/speed tier, Arabic quality, strict-JSON reliability, streaming, free RPM/RPD, and privacy flags (`may_train_on_data`).

| Feature | Primary Requirements | Default Best-Fit Preference Chain |
|---|---|---|
| **`video_script`** | Long output + long context + high Arabic quality + coherence | **Gemini (dedicated keys)** > Other Gemini > Long-context OpenRouter / NVIDIA |
| **`kb_chat` / `chatbot`** | Low latency + streaming + good Arabic + moderate context | **Groq (ultra-fast speed)** > Gemini > OpenRouter / NVIDIA |
| **`quizzes` / `flashcards` / `exams`** | Reliable strict JSON, short outputs, high throughput | **NVIDIA / OpenRouter / DeepInfra / Groq** (JSON throughput) > Gemini |
| **`reports` / `recommendations`** | Strict JSON + analytical reasoning, deterministic (`temp=0.2`) | **Gemini Flash** > Groq > NVIDIA |
| **`question_bank`** | Bulk volume + JSON reliability + Arabic/English + verification | **Groq / Cerebras** (bulk volume) + Gemini (Arabic-heavy) *(Validation uses divergent provider)* |

### ðŸ›¡ï¸ Routing Rules & Self-Healing
* **Dedicated keys**: A key tagged for a feature (e.g. video) is prioritized first for that feature, and acts only as last-resort spillover for other tasks to prevent quota draining.
* **Strict-JSON features**: Validates schema and performs one automatic syntax repair (markdown strip, trailing comma fix) or fast re-prompt repair before rotating.
* **Verification divergence**: Question-bank verification tasks use `exclude_provider` to guarantee verification by a *different* provider than the generator.
* **Privacy protection**: Features touching student data reject models flagged `may_train_on_data=true`.
* **Failure classification**: 429/quota and timeouts trigger backoff + jitter cooling down the whole quota group. 400 bad syntax / safety blocks raise immediately without retrying.

### ðŸ©º Visibility & Diagnostics
* **CLI Diagnostic Command**:
  ```bash
  # View masked keys, quota groups, availability, and routing chains:
  python backend/scripts/llm_diagnostic.py

  # Test connectivity & validate every key live:
  python backend/scripts/llm_diagnostic.py --test-all
  ```
* **Admin REST Endpoints**:
  - `GET /api/admin/llm-status`: Current key pool, health, quota groups, daily usage, and active chains.
  - `POST /api/admin/llm-test`: On-demand live probe test of all keys.
* **Per-Request Operational Logs**:
  `[LLM] feature=video_script provider=gemini model=gemini-2.5-flash key=...SjNg latency=1.24s outcome=SUCCESS`
* **Adding a Provider**: Add adapter spec to `backend/app/core/llm_config.json` (`base_url`, `auth_style`, `default_models`). OpenAI-compatible providers share the generic adapter with zero Python code changes.

### ðŸŽ¬ Video generation tuning
```env
EDUSENSE_VIDEO_NARRATION_WPM=140        # words/min used for duration -> script length
EDUSENSE_VIDEO_SCRIPT_TOLERANCE=0.10    # Â±10% allowed deviation before corrective pass
EDUSENSE_VIDEO_TTS_TIMEOUT=45           # per-scene TTS timeout (seconds)
```

### ðŸ“Š Report thresholds & duration cap
```env
EDUSENSE_REPORT_MIN_EMOTION_SAMPLES=10
EDUSENSE_REPORT_MIN_ATTENDED_MINUTES=2
EDUSENSE_REPORT_MIN_PARTICIPANTS=1
EDUSENSE_REPORT_MAX_ATTENDED_MINUTES=720   # sanity cap; open/left-running sessions clamp, never reject
```

---

## ðŸŒ Grounded Retrieval Pipeline: RAG + Web Search

All content-generating agents follow a strict 3-tier retrieval hierarchy:

```mermaid
flowchart TD
    Req[Generation Request] --> RAG[1. Query ChromaDB Vector Store]
    RAG -->|Chunks Found| GroundRAG[Ground with Curriculum Source Materials]
    RAG -->|0 Chunks| Web[2. Query Web Search Tool via Tavily API]
    Web -->|Results Found| GroundWeb[Ground with Real-World Web Results]
    Web -->|0 Results or Unset| LLM[3. Fall Back to LLM General Knowledge]

    GroundRAG --> Gen[Generate Content + Citation Labels]
    GroundWeb --> Gen
    LLM --> GenUnverified[Generate Content + Mark unverified=True]
```

- **Curriculum RAG First**: Searches course PDFs and session documents in ChromaDB vector embeddings. Cites materials as `[Source: document.pdf p.N]`.
- **Web Search Fallback**: If no relevant curriculum documents exist, queries the Tavily Search API for verified, up-to-date web content. Cites sources as `[Web N: Title](url)`.
- **Graceful Offline Degradation**: If both RAG and Web Search are empty or unavailable, the agent generates content using general model knowledge, flags the result with `unverified: true`, and surfaces an unverified badge in the UI.

---

## âš¡ Smart Multi-Tier AI System (Online + Multi-Model Offline)

EduSense features an **Intelligent Automatic Failover & Task Routing System**:

```text
                   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                   â”‚          AI Agent Request           â”‚
                   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                      â”‚
                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                    â”‚ ðŸŒ Gemini 2.0 Flash (Online API)  â”‚
                    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                      â”‚  (If Offline / Connection Fails)
                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                    â”‚ ðŸ¦™ Specialized Local Ollama LLMs  â”‚
                    â”‚ â€¢ Translation -> Qwen 2.5 (7B)    â”‚
                    â”‚ â€¢ Lessons     -> Mistral (7B)     â”‚
                    â”‚ â€¢ Quizzes     -> Llama 3.1 (8B)   â”‚
                    â”‚ â€¢ Flashcards  -> Llama 3.2 (3B)   â”‚
                    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                      â”‚  (If Ollama Unreachable)
                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                    â”‚ âš™ï¸ Built-in Local Templates        â”‚
                    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

- **Online Mode (Default):** Uses **Google Gemini 2.0 Flash** with automatic multi-key rotation for fast, high-quality generation.
- **Automatic Offline Failover:** If the internet connection drops or Gemini times out (15s limit), the system **automatically failovers** to your local **Ollama** specialized models without throwing errors.
- **Specialized 4-Model Routing:**
  - ðŸŒ **Translation / Multilingual:** Uses `qwen2.5` (Best 7B model for Arabic & 29+ non-English input processing).
  - ðŸ“š **Lessons:** Uses `mistral` (Best 7B model for structured lessons, slide outlines & teaching scripts).
  - ðŸ“ **Quizzes:** Uses `llama3.1` (Best 8B reasoning for assessment questions & distractors).
  - ðŸŽ´ **Flashcards & General:** Uses `llama3.2` (Lightweight 3B model for fast card generation).
- **Template Fallback:** If Ollama is also unreachable, built-in deterministic templates prevent application crashes.

---

## ðŸ“Š Emotion Model Benchmark (v7 EfficientNet-B0 â€” 90.9%)

Our custom trained **v7 PyTorch EfficientNet-B0** model achieves **90.9% overall accuracy**:

| Emotion Class | Accuracy | Sample Size (n) | Benchmark Winner |
| :--- | :--- | :--- | :--- |
| **Angry** | **88.6%** | n=1210 | ðŸ† **v7** |
| **Disgust** | **94.7%** | n=226 | ðŸ† **v7** |
| **Fear** | **87.3%** | n=1185 | ðŸ† **v7** |
| **Happy** | **94.1%** | n=715 | ðŸ† **v7** |
| **Neutral** | **95.5%** | n=378 | ðŸ† **v7** |
| **Sad** | **94.3%** | n=297 | ðŸ† **v7** |
| **Surprise** | **96.4%** | n=193 | ðŸ† **v7** |
| **Overall Model** | **90.9%** | **Total Benchmark** | ðŸ† **v7 EfficientNet-B0** |

---

## ðŸ”’ Privacy & Consent

Before any webcam capture starts, students must explicitly opt in â€” consent is tracked **separately per purpose**:

- **`emotion_detection`** â€” real-time emotion analysis during live sessions.
- **`quiz_anti_cheat`** â€” camera-based proctoring during timed quizzes.

Consent is enforced **server-side**, declining never blocks access to non-camera platform areas, and users can withdraw consent at any time. See [`docs/PRIVACY_POLICY.md`](docs/PRIVACY_POLICY.md) and [`docs/TERMS_OF_SERVICE.md`](docs/TERMS_OF_SERVICE.md).

---

## ðŸš€ Quick Start Guide

### 1. Backend Setup (FastAPI + SQLAlchemy)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # Configure your keys in .env
python migrate.py upgrade   # Apply all Alembic database migrations
uvicorn app.main:app --reload
```

### 2. Frontend Setup (React + Vite + TailwindCSS)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

**Default Test Credentials:**
- **Instructor:** `instructor@edusense.local` / `Password123`
- **Student:** `student@edusense.local` / `Password123`

> âš ï¸ **Production note:** set `EDUSENSE_DISABLE_DEFAULT_ACCOUNTS=true` in `.env` to prevent default seed accounts from being created in production deployments.

---

## ðŸ¦™ Running Ollama Offline (Multi-Model Setup)

1. Download Ollama from [ollama.com](https://ollama.com).
2. Pull the 4 specialized models in your terminal:
   ```bash
   ollama pull qwen2.5     # Translation & Multilingual (7B)
   ollama pull mistral     # Lessons & Scripts (7B)
   ollama pull llama3.1    # Quizzes & Assessments (8B)
   ollama pull llama3.2    # Flashcards & General Fallback (3B)
   ```
3. Update `backend/.env`:
   ```env
   EDUSENSE_AI_PROVIDER=ollama
   ```

---

## ðŸ“§ Email Notifications Setup & Workflow (Gmail SMTP)

EduSense includes an automated background scheduler (`APScheduler`) that queries upcoming sessions every minute and sends automated HTML reminder emails to students and instructors 15 to 1 minutes before class starts.

```mermaid
sequenceDiagram
  autonumber
  participant SCH as â±ï¸ APScheduler (Every 1 min)
  participant DB as ðŸ—„ï¸ Database (Sessions & Registrations)
  participant SMTP as ðŸ“§ Gmail SMTP Server
  participant USER as ðŸ“¬ Student & Instructor Inboxes

  SCH->>DB: Query pending sessions starting in <= 15 minutes
  DB-->>SCH: Return matching sessions & registered emails
  SCH->>SCH: Check if reminder already sent for current minute
  alt SMTP Credentials configured in .env
    SCH->>SMTP: Send HTML reminder email via TLS (Port 587)
    SMTP-->>USER: Deliver "Session starting soon!" email with direct link
    SCH->>DB: Record minute index in reminders_sent column
  else SMTP Credentials missing / blank
    SCH->>SCH: Log warning & skip sending (Zero crashes / graceful fallback)
  end
```

### âš™ï¸ Configuration in `backend/.env`:

```env
# Email SMTP notifications:
EDUSENSE_SMTP_HOST=smtp.gmail.com
EDUSENSE_SMTP_PORT=587
EDUSENSE_SMTP_USER=your-email@gmail.com
EDUSENSE_SMTP_PASSWORD=your-16-character-app-password
```
*(Generate an App Password via Google Account â†’ Security â†’ 2-Step Verification â†’ App Passwords).*

---

## ðŸ“ Project Architecture

```text
frontend/     React + Vite frontend, interactive dashboards, webcam capture
  src/
    components/ Shared UI widgets, Layout, Charts, ConsentModal, SessionPickerFields...
    context/    AuthContext (token reactivity), GenerationJobContext, ToastContext...
    pages/      Dashboard, LiveSessionRoom, Quiz, StudentExams, StudentAssignments, KnowledgeBase, AITools...
backend/      FastAPI REST backend, PostgreSQL / SQLite ORM, JWT auth
  app/
    agents/   8 Specialized AI agents + orchestrator + scope guardrails + RAG/Web tools
    api/      REST routes (auth, sessions, ai, quizzes, assignments, reports, rag, users, admin)
    core/     Settings, scheduler, security, audit logging
    db/       Session engine, seed.py with safe DDL migrations
    models/   SQLAlchemy ORM models (Users, Quizzes, Assignments, VideoProjects, ChatMessages...)
    schemas/  Pydantic schemas with strict validation
    services/ Gemini client (with failover rotation), Ollama runner, RAG service, Video studio, Export
  migrations/ Alembic migrations tracking schema revisions up to c59128f_harden_schema_task10
docs/         Architecture blueprints, workflow flowcharts, Privacy Policy, Terms of Service, HTTPS setup
```

---

## ðŸ‘¨â€ðŸ’» Author & Contact

Developed by **[Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)**
ðŸ”— **LinkedIn:** [https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
ðŸ™ **GitHub:** [https://github.com/adel-noufal](https://github.com/adel-noufal)
