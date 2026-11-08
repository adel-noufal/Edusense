# 🎓 EduSense — Multi-Agent AI Education Platform

[![Author](https://img.shields.io/badge/Author-Adel_Mohamed_Noufal-blue.svg)](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Adel_Mohamed_Noufal-0A66C2.svg?logo=linkedin)](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
[![Emotion Model](https://img.shields.io/badge/PyTorch-v7_EfficientNet--B0_(90.9%25)-EE4C2C.svg?logo=pytorch)](https://github.com/adel-noufal/Edusense)
[![AI Backend](https://img.shields.io/badge/AI_Providers-Gemini_2.0_%7C_Ollama-4285F4.svg)](https://github.com/adel-noufal/Edusense)
[![Stack](https://img.shields.io/badge/Stack-React_18_%7C_FastAPI_%7C_PostgreSQL-00599C.svg)](https://github.com/adel-noufal/Edusense)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0.0-blueviolet.svg)](CHANGELOG.md)
[![CI/CD](https://github.com/adel-noufal/Edusense/actions/workflows/ci.yml/badge.svg)](https://github.com/adel-noufal/Edusense/actions)

> **EduSense** is a fully local, multi-agent AI Education Platform designed for adaptive learning, automated lesson & assessment generation, real-time webcam emotion recognition, and interactive educational content creation.
>
> 👤 **Author:** [Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)  
> 🔗 **LinkedIn:** [https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)  
> 🔗 **GitHub Repository:** [https://github.com/adel-noufal/Edusense](https://github.com/adel-noufal/Edusense)

---

## 🌟 Key Features & AI Architecture

EduSense runs **8 specialized AI agents**, coordinated sequentially by `EduSenseAgentWorkflow` ([`backend/app/agents/workflow.py`](file:///D:/Adel/Projects/Edusense%202/backend/app/agents/workflow.py)):

1. 🎭 **Emotion Analysis Agent** — Analyzes webcam frames in real-time using a custom **v7 PyTorch EfficientNet-B0** model (**90.9% Accuracy**) with DeepFace fallback.
2. 📊 **Student Engagement Agent** — Computes real-time engagement and attention metrics from emotion distributions.
3. 💡 **Recommendation Agent** — Generates pedagogical interventions when engagement drops below threshold (< 62%).
4. 📚 **Lesson Generation Agent** — Generates structured lessons, slides, outlines, and teaching scripts (RAG-grounded).
5. 📝 **Quiz Generation Agent** — Generates adaptive MCQs, True/False, and short-answer questions (RAG-grounded), with instructor-configurable timers and reusable `QuizAgentConfig` presets.
6. 🎴 **Flashcard Generation Agent** — Produces study flashcard decks (RAG-grounded).
7. 📄 **Report Generation Agent** — Generates executive PDF reports via `ReportLab`.
8. 🧠 **RAG Knowledge Base & AI Chat Assistant** — Grounded PDF course material retrieval via ChromaDB vector embeddings, interactive AI Chat (`POST /api/rag/ask`), instructor suggestions (`GET /api/rag/suggest`), and Knowledge Base Admin Dashboard (`/instructor/knowledge-base`).

---

## 🗺️ Roadmap

- ✅ **RAG System**: DONE — vector store (ChromaDB), dual ingestion paths (general `/api/rag/ingest` + auto-ingest on session resource upload), `RAG_Search_Tool`, RAG grounding in Lesson/Quiz/Flashcard agents (with `sources`/`unverified` badges), `Web_Search_Tool`, agent orchestrator with 4 failover states, chatbot (`/api/ai/chat`, rate-limited, with persisted conversation history), shared scope guardrail + audit logging across all LLM-calling agents (including the offline template fallback tier).
- ✅ **Security Hardening**: DONE — Argon2 password hashing (with backward-compatible fallback), role-based access control audited and enforced across every API endpoint, structured audit logging (database + file) for auth/sessions/reports/users/admin actions, rate limiting on auth and chat endpoints, `DISABLE_DEFAULT_ACCOUNTS` env flag for production, documented HTTPS/TLS deployment setup, CI security scanning (pip-audit, CodeQL, Trivy, TruffleHog).
- ✅ **Quiz Timer & Anti-Cheat**: DONE — per-quiz/per-question timers with server-side time validation, Quiz AI Agent Generator (`QuizAgentConfig` — reusable instructor presets for difficulty, question types, topic weighting, timer, and anti-cheat settings), fullscreen lockdown with exit-attempt detection (tab switch, window blur, fullscreen exit), dynamic traceable watermark overlay, optional camera-based second-device detection, instructor violation review with explicit re-entry approval (no auto re-enable).
- ✅ **Privacy & Consent**: DONE — granular webcam consent tracked separately per purpose (`emotion_detection` vs. `quiz_anti_cheat`), enforced server-side (not just hidden in the UI), declining consent never blocks non-camera platform access, draft Privacy Policy and Terms of Service (see `docs/PRIVACY_POLICY.md` and `docs/TERMS_OF_SERVICE.md` — **draft text, pending legal review before production use**, especially given minors are involved).
- 🔄 **Engagement Model**: IN PROGRESS — replacing the current emotion-classifier-derived engagement score with a separately trained, calibrated model (training underway on a dedicated dataset).

---

## 👨‍🏫 Instructor System Workflow

```mermaid
sequenceDiagram
  autonumber
  actor I as Instructor
  participant UI as React Frontend
  participant API as FastAPI Backend
  participant WF as 7-Agent Workflow
  participant PDF as ReportLab Service

  I->>UI: 1. Create & Schedule Class Session
  UI->>API: POST /api/sessions
  API->>UI: Session Created & Email Reminders Scheduled
  I->>UI: 2. Launch Live Session Room
  UI->>API: GET /api/sessions/{id}/emotions/distribution (Polling)
  API->>UI: Real-time Emotion % & Engagement Timeline
  UI->>I: Displays Engagement Alert (if < 62%)
  I->>UI: 3. Trigger AI Session Improvement Loop
  UI->>API: POST /api/ai/workflow/improve
  API->>WF: Executes EduSenseAgentWorkflow
  WF-->>API: Returns Simplified Lesson, Adaptive Quiz & Summary
  API->>PDF: Generate Session Report PDF
  PDF-->>UI: Download Link for Executive PDF Report
```

---

## 🎓 Student System Workflow

```mermaid
sequenceDiagram
  autonumber
  actor S as Student
  participant UI as React Frontend
  participant Cam as Webcam Processor
  participant API as FastAPI Backend
  participant ML as PyTorch EfficientNet-B0 v7

  S->>UI: 1. Register & Join Live Classroom
  UI->>Cam: Initialize Webcam Stream
  loop Every N seconds
    Cam->>UI: Capture Frame (Base64 JPEG)
    UI->>API: POST /api/sessions/{id}/emotions
    API->>ML: Classify Emotion (v7 EfficientNet-B0)
    ML-->>API: Emotion (Happy, Neutral, Confused, Sad, etc.) + Confidence
    API-->>UI: Emotion Log Saved
  end
  S->>UI: 2. Access AI Tools (Adaptive Flashcards & Quizzes)
  UI->>API: POST /api/ai/flashcards / POST /api/ai/quiz
  API-->>UI: Interactive Flashcard Decks & Knowledge Checks
  S->>UI: 3. Receive Practice Feedback & Progress Stats
```

---
                   ┌─────────────────────────────────────┐
                   │          AI Agent Request           │
                   └──────────────────┬──────────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │ 🌐 Gemini 2.0 Flash (Online API)  │
                    └─────────────────┬─────────────────┘
                                      │  (If Offline / Connection Fails)
                    ┌─────────────────▼─────────────────┐
                    │ 🦙 Specialized Local Ollama LLMs  │
                    │ • Translation -> Qwen 2.5 (7B)    │
                    │ • Lessons     -> Mistral (7B)     │
                    │ • Quizzes     -> Llama 3.1 (8B)   │
                    │ • Flashcards  -> Llama 3.2 (3B)   │
                    └─────────────────┬─────────────────┘
                                      │  (If Ollama Unreachable)
                    ┌─────────────────▼─────────────────┐
                    │ ⚙️ Built-in Local Templates        │
                    └───────────────────────────────────┘


- **Online Mode (Default):** Uses **Google Gemini 2.0 Flash** for fast, high-quality generation.
- **Automatic Offline Failover:** If the internet connection drops or Gemini times out (15s limit), the system **automatically failovers** to your local **Ollama** specialized models without throwing errors.
- **Specialized 4-Model Routing:**
  - 🌐 **Translation / Multilingual:** Uses `qwen2.5` (Best 7B model for Arabic & 29+ non-English input processing).
  - 📚 **Lessons:** Uses `mistral` (Best 7B model for structured lessons, slide outlines & teaching scripts).
  - 📝 **Quizzes:** Uses `llama3.1` (Best 8B reasoning for assessment questions & distractors).
  - 🎴 **Flashcards & General:** Uses `llama3.2` (Lightweight 3B model for fast card generation).


- **Template Fallback:** If Ollama is also unreachable, built-in deterministic templates prevent application crashes. The offline template path still applies the same scope guardrail as the online tiers.

---

## 📊 Emotion Model Benchmark (v7 EfficientNet-B0 — 90.9%)

Our custom trained **v7 PyTorch EfficientNet-B0** model achieves **90.9% overall accuracy**:

| Emotion Class | Accuracy | Sample Size (n) | Benchmark Winner |
| :--- | :--- | :--- | :--- |
| **Angry** | **88.6%** | n=1210 | 🏆 **v7** |
| **Disgust** | **94.7%** | n=226 | 🏆 **v7** |
| **Fear** | **87.3%** | n=1185 | 🏆 **v7** |
| **Happy** | **94.1%** | n=715 | 🏆 **v7** |
| **Neutral** | **95.5%** | n=378 | 🏆 **v7** |
| **Sad** | **94.3%** | n=297 | 🏆 **v7** |
| **Surprise** | **96.4%** | n=193 | 🏆 **v7** |
| **Overall Model** | **90.9%** | **Total Benchmark** | 🏆 **v7 EfficientNet-B0** |

---

## 🔒 Privacy & Consent

Before any webcam capture starts, students must explicitly opt in — consent is tracked **separately per purpose**:

- **`emotion_detection`** — real-time emotion analysis during live sessions.
- **`quiz_anti_cheat`** — camera-based proctoring during timed quizzes.

Consent is enforced **server-side** (not just hidden by the UI), declining never blocks access to the rest of the platform, and users can withdraw consent at any time. See [`docs/PRIVACY_POLICY.md`](docs/PRIVACY_POLICY.md) and [`docs/TERMS_OF_SERVICE.md`](docs/TERMS_OF_SERVICE.md).

> ⚠️ These are **draft policies** and must be reviewed by a lawyer before production use, particularly given the involvement of minors.

---

## 🚀 Quick Start Guide

### 1. Backend Setup (FastAPI + SQLAlchemy)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # Configure your keys in .env
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

> ⚠️ **Production note:** set `EDUSENSE_DISABLE_DEFAULT_ACCOUNTS=true` in `.env` to prevent these default accounts from being created in a production deployment.

---

## 🦙 Running Ollama Offline (Multi-Model Setup)

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

## 📧 Email Notifications Setup & Workflow (Gmail SMTP)

EduSense includes an automated background scheduler (`APScheduler`) that queries upcoming sessions every minute and sends automated HTML reminder emails to students and instructors 15 to 1 minutes before a class starts.

### 🔄 Email SMTP Sequence Diagram

```mermaid
sequenceDiagram
  autonumber
  participant SCH as ⏱️ APScheduler (Every 1 min)
  participant DB as 🗄️ Database (Sessions & Registrations)
  participant SMTP as 📧 Gmail SMTP Server
  participant USER as 📬 Student & Instructor Inboxes

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

### ⚙️ Configuration in `backend/.env`:

```env
EDUSENSE_SMTP_HOST=smtp.gmail.com
EDUSENSE_SMTP_PORT=587
EDUSENSE_SMTP_USER=your-email@gmail.com
EDUSENSE_SMTP_PASSWORD=your-16-character-app-password
```
*(Generate an App Password via Google Account → Security → 2-Step Verification → App Passwords).*

---

## 📁 Project Architecture

```text
frontend/     React + Vite frontend, interactive dashboards, webcam capture
backend/      FastAPI REST backend, PostgreSQL / SQLite ORM, JWT auth
  app/
    agents/   7 Specialized AI agents + EduSenseAgentWorkflow orchestrator + shared scope guardrail
    api/      REST API route definitions (auth, sessions, AI tools, quizzes, reports, RAG, consent, admin)
    core/     Settings, scheduler, security, audit logging
    services/ Gemini API client, Ollama runner, PDF/Word/PPTX export services
docs/         Architecture blueprints, workflow flowcharts, Privacy Policy, Terms of Service, HTTPS/TLS setup
```

---

## 👨‍💻 Author & Contact

Developed by **[Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)**  
🔗 **LinkedIn:** [https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)  
🐙 **GitHub:** [https://github.com/adel-noufal](https://github.com/adel-noufal)
## ⚡ Smart Multi-Tier AI System (Online + Multi-Model Offline)

EduSense features an **Intelligent Automatic Failover & Task Routing System**:
