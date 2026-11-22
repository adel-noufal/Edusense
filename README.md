# EduSense — Multi-Agent AI Education Platform

[![Author](https://img.shields.io/badge/Author-Adel_Mohamed_Noufal-blue.svg)](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
[![Stack](https://img.shields.io/badge/Stack-React_18_%7C_FastAPI_%7C_SQLite_%2F_PostgreSQL-00599C.svg)]()
[![AI](https://img.shields.io/badge/AI-Free--tier_cloud_%2B_local_Ollama-4285F4.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.1.1-blueviolet.svg)](CHANGELOG.md)
[![CI](https://github.com/adel-noufal/Edusense/actions/workflows/ci.yml/badge.svg)](https://github.com/adel-noufal/Edusense/actions)

EduSense is an AI teaching platform for schools, universities and training teams. Instructors
create lessons, quizzes, flashcards, reports and narrated videos from their own course
material; students join live sessions, take assessments and study with a grounded assistant.

It is **hybrid by design**: content is generated with **free-tier cloud models** when the
machine is online, and with **local Ollama models** when it is not. Nothing is described as
"fully local" here — cloud providers are part of the normal path, and the offline tier is a
feature on top of it, not a replacement for it.

- **Author:** [Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
- **Repository:** <https://github.com/adel-noufal/Edusense>

---

## Who it is for

| Role | What EduSense does for them |
| --- | --- |
| Instructors / lecturers | Turn a PDF or a topic into a lesson, quiz, flashcard deck, PDF report or narrated video; run live classes and see engagement |
| Students | Join sessions, take proctored exams and assignments, ask questions grounded in the uploaded course material, revise with flashcards |
| Institutions | One self-hostable application, per-user data, no per-seat licence, free-tier-only AI routing by default |

---

## Features by portal

### Instructor
- **AI Lessons** — structured objectives, sections, slides, key points and summary, grounded in
  the session's uploaded material first, web search second, model knowledge last.
- **Quizzes & exams** — AI-generated or manually authored MCQs / true-false / short answers,
  publishable as a proctored exam or a homework assignment with timers and anti-cheat options.
- **Flashcards** — distinct study cards, exportable as JSON / Markdown / HTML / CSV.
- **Video studio** — narrated scene-based lesson video, interactive player with chapters,
  transcript, playback speed and checkpoints; MP4 export when FFmpeg is available.
- **Knowledge Base** — upload PDF/DOCX/PPTX/TXT, background ingestion into ChromaDB, per-file
  Q&A, persistent conversation history, and a strict "answer only from these documents" mode.
- **Reports** — executive PDF and CSV reports with attended minutes, emotion distribution and
  an explicit "not enough data yet" state instead of invented numbers.
- **Live classroom** — screen sharing, student presence, real-time emotion telemetry (with
  consent), engagement alerts.

### Student
- Session browsing, one-click registration and countdown.
- Live classroom with camera-based emotion analysis (consent required, per purpose).
- Assessment hub for exams (fullscreen lockdown, timers, watermark) and assignments.
- Grounded AI assistant and flashcards for revision.
- Emotion recognition trial widget on the dashboard (not stored).

### Shared
- JWT authentication with instructor / student / admin roles.
- English and Arabic interface with full RTL layout.
- Light/dark theme, responsive layouts for laptop, tablet and phone.

---

## Architecture

```text
frontend/            React 18 + Vite + TailwindCSS
  src/pages          dashboards, AI tools, Knowledge Base, live room, assessments
  src/components     shared UI, webcam capture, consent modal, charts
  src/i18n           English/Arabic dictionary and RTL handling

backend/             FastAPI + SQLAlchemy + Alembic
  app/agents         8 agents + orchestrator + scope guardrails
  app/api            REST routes (auth, sessions, ai, quizzes, rag, reports, videos)
  app/services       LLM router, RAG/ingestion, video, export, attendance, email
  app/tools          doctor, launcher, diagnostics
  tests/             pytest suite (live provider calls are opt-in)

data/chroma          persistent vector store (created at runtime, not committed)
docs/                architecture, API, privacy, terms, demo notes
```

Request flow for any generated artefact:

```text
Instructor request
   -> RAG over the session's documents (ChromaDB, all-MiniLM-L6-v2)
   -> optional Tavily web grounding when no document matches
   -> LLM router (free-tier cloud providers, then local Ollama offline)
   -> answer sanitizer (no prompt leakage) + verified/unverified badge in the UI
```

---

## AI routing: free tier only, by default

`ALLOW_PAID_MODELS=false` is the default and the router obeys it. A model is offered only if it
is free (free tier, free credits, or a local model). Providers are grouped by strength:

| Feature | Primary | Secondary | Tertiary | Offline |
| --- | --- | --- | --- | --- |
| Video scripts, long lessons, Arabic, large PDFs | Gemini 2.5 Flash (1M context) | Gemini 2.5 Pro | NVIDIA / OpenRouter `:free` | mistral / qwen2.5 |
| Knowledge Base and chatbot (latency-sensitive) | Groq | Gemini 2.5 Flash | OpenRouter `:free` | qwen2.5 |
| Quizzes, exams, strict JSON | NVIDIA (2 keys, load-balanced) | Groq / OpenRouter `:free` | Gemini | llama3.1 |
| Answer-key verification | model from a **different family** than the generator | — | — | llama3.1 |
| Flashcards, prompt enhancement (small tasks) | Groq | llama3.2 (Ollama) | Gemini | llama3.2 |
| Reports and recommendations | Gemini 2.5 Flash (temperature 0.2) | Groq | NVIDIA | mistral |

Rules enforced by the router (`backend/app/services/llm.py`, `app/core/llm_config.json`):

- Unlimited keys per provider; keys are rotated round-robin, quota groups cool down together
  after a 429.
- Strict-JSON features validate the schema and try one repair before rotating.
- Dead models (404/410) are removed by live `/models` discovery instead of being offered.
- Student-data features refuse models flagged `may_train_on_data`.
- Small tasks never burn the long-context Gemini quota.

Every generation response carries the provider and model that produced it, and
`GET /api/ai/available-models` returns the live list with badges (`Free`, `Free - rate limited`,
`Offline`).

### Quality pipeline
1. Retrieval grounding (documents → web → model knowledge, each labelled).
2. Prompt with scope guardrails and language/duration/count constraints.
3. Schema validation and one repair pass for JSON features.
4. Divergent-model verification for answer keys.
5. Teaching-style profiles that change structure, not just wording.
6. UI badges for verified / unverified content.

---

## Quick start (Windows)

Requirements: Python 3.11+, Node.js 18+, and — for video export — FFmpeg.

```bat
install-local.bat        :: creates backend\.venv, installs Python and npm packages
copy backend\.env.example backend\.env
notepad backend\.env     :: add your free API keys (see below)
start-all.bat            :: doctor + backend (8000/8001) + frontend (5173)
```

Verify the whole installation at any time:

```bat
verify.bat               :: doctor, tests, layout/emotion check, frontend build,
                         :: secret scan, UTF-8 mojibake scan, pytest collection
```

`doctor` checks the venv, packages, `.env`, database migrations, port bindability, FFmpeg
(including WinGet install locations), LibreOffice, Playwright/Chromium, Ollama and its models,
that `app.main` imports, and that the persisted Knowledge Base embedding model loads.

Frontend: <http://localhost:5173> · API docs: <http://localhost:8000/docs>

---

## Configuration

Keys live in `backend/.env` (never committed). Any number of keys per provider is supported.

| Variable pattern | Meaning |
| --- | --- |
| `GEMINI_API_KEY`, `EDUSENSE_GEMINI_API_KEY`, `GEMINI_API_KEY_1..n` | Gemini keys (legacy names still supported) |
| `<PROVIDER>_API_KEYS=key1,key2` | Pooled keys, e.g. `GROQ_API_KEYS`, `NVIDIA_API_KEYS`, `OPENROUTER_API_KEYS` |
| `<PROVIDER>_KEY_<LABEL>` | Named key, e.g. `GEMINI_KEY_VIDEO_1`, `GROQ_KEY_CHAT` |
| `<PROVIDER>_KEY_<LABEL>_GROUP` | Quota group — keys in one group cool down together |
| `<PROVIDER>_KEY_<LABEL>_FEATURE` | Pin a key to a feature (`video_script`, `quizzes`, `chatbot`, …) |
| `<PROVIDER>_KEY_<LABEL>_PRIORITY` | 1–100, higher is tried first |

Application settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `EDUSENSE_DATABASE_URL` | `sqlite:///./edusense.db` | Database connection (SQLite or PostgreSQL) |
| `EDUSENSE_SECRET_KEY` | — | JWT signing secret (required) |
| `ALLOW_PAID_MODELS` | `false` | Keep `false` for free-tier-only routing |
| `EDUSENSE_AI_PROVIDER` | auto | Force `gemini` / `ollama` / cloud routing |
| `EDUSENSE_OLLAMA_URL` | `http://localhost:11434` | Local model server |
| `EDUSENSE_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Must match the persisted Chroma collection |
| `EDUSENSE_FFMPEG_PATH` / `EDUSENSE_FFPROBE_PATH` | auto | Explicit binary paths when not on `PATH` |
| `EDUSENSE_VIDEO_NARRATION_WPM` | `140` | Words per minute used for script length |
| `EDUSENSE_VIDEO_SCRIPT_TOLERANCE` | `0.10` | Allowed deviation from the requested duration |
| `EDUSENSE_VIDEO_TTS_TIMEOUT` | `45` | Per-scene TTS timeout (seconds) |
| `EDUSENSE_REPORT_MIN_*` / `MAX_ATTENDED_MINUTES` | see `config.py` | Report sufficiency thresholds and duration cap |
| `EDUSENSE_SMTP_*` | unset | Optional email reminders (Gmail app password) |
| `EDUSENSE_DISABLE_DEFAULT_ACCOUNTS` | `false` | Set `true` in production |

`ALLOW_PAID_MODELS=true` is the only way to see paid models. Demo accounts for local testing are
documented in [`docs/DEV.md`](docs/DEV.md) and are marked demo-only; they are not production
credentials.

---

## Running offline

EduSense uses whatever Ollama models are **already installed** — it never pulls a model on its
own. The reference setup (and the routing defaults) use four:

| Model | Role |
| --- | --- |
| `qwen2.5` | Arabic and multilingual, translation |
| `mistral` | lessons and scripts |
| `llama3.1` | quizzes and assessments |
| `llama3.2` | flashcards and small/fast tasks |

With Ollama running and the models present, disconnect the network and the router falls through
to these local models automatically. `doctor` reports which of the four are detected. To check
offline behaviour yourself: start `start-all.bat`, disable Wi-Fi/Ethernet, then generate a
lesson, quiz or flashcard deck — the result carries an `Offline` provider label.

Deterministic templates remain the last resort so the UI never crashes when both cloud and
Ollama are unavailable.

---

## Testing

```bat
cd backend
.venv\Scripts\python.exe -m pytest -q -m "not live_provider"
```

- `live_provider` tests call real APIs and are skipped unless `RUN_LIVE_PROVIDERS=1`.
- `verify.bat` adds the doctor, a Playwright layout/emotion check, the frontend build, a secret
  scan, the UTF-8 mojibake scan, and `pytest --collect-only`.
- The mojibake gate (`scripts/mojibake_scan.py`) fails on any double-encoded UTF-8 in tracked
  files; it runs in `verify.bat` and in CI.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `WinError 10013` binding port 8000 | Another service owns the port. The launcher picks 8001 automatically; or `netstat -ano \| findstr :8000` then stop that PID |
| `ImportError` / `charset_normalizer` or `re.PatternError` from a site-package | A corrupted or mismatched dependency in the venv. `pip install --force-reinstall -r requirements.txt` |
| `Embedding function conflict: new: onnx_mini_lm_l6_v2 vs persisted: sentence_transformer` | `sentence-transformers` failed to import, so the code used to fall back to ONNX. EduSense now refuses the switch and names the cause; reinstall requirements so the persisted model loads. Never mix embedding models in one collection |
| `MP4 export depends on FFmpeg` | FFmpeg not on the backend `PATH`. Install with `winget install Gyan.FFmpeg`, then rerun `doctor`; or set `EDUSENSE_FFMPEG_PATH` |
| PPTX/DOCX rendering issues | LibreOffice is required for high-fidelity conversion; `doctor` reports its path |
| Knowledge Base shows an error | The message now distinguishes a network failure (with the real API base URL) from an HTTP error (with status and server detail) |

---

## Security notes

- Webcam capture requires explicit consent, tracked separately for emotion detection and exam
  proctoring, and enforced server-side; declining never blocks non-camera features.
- Secrets belong in `backend/.env` only. `verify.bat` scans tracked files for credential
  patterns, and CI never receives real keys.
- Student-data features reject models that may train on submitted data.
- Set `EDUSENSE_DISABLE_DEFAULT_ACCOUNTS=true` before any public deployment.
- See [`docs/PRIVACY_POLICY.md`](docs/PRIVACY_POLICY.md) and
  [`docs/TERMS_OF_SERVICE.md`](docs/TERMS_OF_SERVICE.md).

---

## Honest limitations

- **Emotion accuracy depends on the camera and lighting.** The 90.9% figure is a
  **dataset benchmark** of the v7 EfficientNet-B0 model on its evaluation split — it is not
  live-webcam accuracy in a classroom, which is lower and varies by device, pose and light.
- Live sessions use polling for telemetry, not a media server; very large classes need tuning.
- Video generation produces narrated, scene-based explanatory videos. It is not a generative
  text-to-video model, and MP4 export requires FFmpeg.
- Free tiers are rate-limited. Heavy institutional use will hit provider quotas and fall through
  to local models or templates.
- The Arabic interface is complete for the shipped strings; user-generated Arabic content
  quality depends on the selected model.
- No committed screenshots or demo video are shipped in this repository yet; capture them from
  your own running instance.

---

## Roadmap

- [x] RAG knowledge base with background ingestion (PDF/DOCX/PPTX/TXT)
- [x] Multi-provider, multi-key LLM router with free-tier enforcement
- [x] Offline Ollama tier with per-task model roles
- [x] Proctored exams and assignments with timers and anti-cheat
- [x] CSV (UTF-8 BOM) and PDF reports with data-sufficiency states
- [x] Arabic UI, RTL, Arabic document export
- [ ] Motion-graphics video renderer (animated scenes captured frame-by-frame)
- [ ] Real-time telemetry over WebSockets instead of polling
- [ ] Institution-level SSO (SAML/OIDC)
- [ ] Committed screenshots and a recorded demo video

---

## Credits and licences

EduSense is released under the [MIT License](LICENSE).

Third-party components (all permissively licensed):

| Component | Licence |
| --- | --- |
| FastAPI, Uvicorn, Starlette | MIT / BSD |
| SQLAlchemy, Alembic | MIT |
| Pydantic | MIT |
| React, Vite, TailwindCSS, lucide-react | MIT |
| ChromaDB | Apache-2.0 |
| sentence-transformers, PyTorch, torchvision | Apache-2.0 / BSD-style |
| transformers, Hugging Face models (all-MiniLM-L6-v2) | Apache-2.0 |
| OpenCV, NumPy | Apache-2.0 / BSD-3-Clause |
| DeepFace | MIT |
| ReportLab | BSD |
| python-docx, python-pptx | MIT |
| pypdf, gTTS | BSD-3-Clause / MIT |
| Ollama, Qwen2.5, Mistral, Llama 3.1/3.2 | MIT / Apache-2.0 / Llama Community Licence — check each model card before redistribution |

Model outputs are the responsibility of the deploying institution; verify AI-generated
assessment content before publishing it to students.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Branch from `main`, keep `verify.bat` green, and open a
pull request. Commits that fail the encoding gate or the test suite are not merged.
