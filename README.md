# 🎓 EduSense — Multi-Agent AI Education Platform

[![Author](https://img.shields.io/badge/Author-Adel_Mohamed_Noufal-blue.svg)](https://github.com/adel-noufal)
[![GitHub Repository](https://img.shields.io/badge/GitHub-Edusense-black.svg?logo=github)](https://github.com/adel-noufal/Edusense)
[![Emotion Model](https://img.shields.io/badge/PyTorch-v7_EfficientNet--B0_(90.9%25)-EE4C2C.svg?logo=pytorch)](https://github.com/adel-noufal/Edusense)
[![AI Backend](https://img.shields.io/badge/AI_Providers-Gemini_2.0_%7C_Ollama-4285F4.svg)](https://github.com/adel-noufal/Edusense)
[![Stack](https://img.shields.io/badge/Stack-React_18_%7C_FastAPI_%7C_PostgreSQL-00599C.svg)](https://github.com/adel-noufal/Edusense)

> **EduSense** is a fully local, multi-agent AI Education Platform designed for adaptive learning, automated lesson & assessment generation, real-time webcam emotion recognition, and interactive educational content creation.
>
> 👤 **Author:** [Adel Mohamed Noufal](https://github.com/adel-noufal)  
> 🔗 **Repository:** [github.com/adel-noufal/Edusense](https://github.com/adel-noufal/Edusense)

---

## 🌟 Key Features & AI Architecture

EduSense runs **7 specialized AI agents**, coordinated sequentially by `EduSenseAgentWorkflow` ([`backend/app/agents/workflow.py`](file:///D:/Adel/Projects/Edusense%202/backend/app/agents/workflow.py)):

1. 🎭 **Emotion Analysis Agent** — Analyzes webcam frames in real-time using a custom **v7 PyTorch EfficientNet-B0** model (**90.9% Accuracy**) with DeepFace fallback.
2. 📊 **Student Engagement Agent** — Computes real-time engagement and attention metrics from emotion distributions.
3. 💡 **Recommendation Agent** — Generates pedagogical interventions when engagement drops below threshold (< 62%).
4. 📚 **Lesson Generation Agent** — Generates structured lessons, slides, outlines, and teaching scripts.
5. 📝 **Quiz Generation Agent** — Generates adaptive MCQs, True/False, and short-answer questions.
6. 🎴 **Flashcard Generation Agent** — Produces study flashcard decks.
7. 📄 **Report Generation Agent** — Generates executive PDF reports via `ReportLab`.

---

## ⚡ Smart Multi-Tier AI System (Online + Multi-Model Offline)

EduSense features an **Intelligent Automatic Failover & Task Routing System**:

```
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
```

- **Online Mode (Default):** Uses **Google Gemini 2.0 Flash** for fast, high-quality generation.
- **Automatic Offline Failover:** If the internet connection drops or Gemini times out (15s limit), the system **automatically failovers** to your local **Ollama** specialized models without throwing errors.
- **Specialized 4-Model Routing:**
  - 🌐 **Translation / Multilingual:** Uses `qwen2.5` (Best 7B model for Arabic & 29+ non-English input processing).
  - 📚 **Lessons:** Uses `mistral` (Best 7B model for structured lessons, slide outlines & teaching scripts).
  - 📝 **Quizzes:** Uses `llama3.1` (Best 8B reasoning for assessment questions & distractors).
  - 🎴 **Flashcards & General:** Uses `llama3.2` (Lightweight 3B model for fast card generation).


- **Template Fallback:** If Ollama is also unreachable, built-in deterministic templates prevent application crashes.

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

---

## 🦙 Running Ollama Offline (Multi-Model Setup)

1. Download Ollama from [ollama.com](https://ollama.com).
2. Pull the 3 specialized models in your terminal:
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

## 📧 Email Notifications Setup (Gmail SMTP)

EduSense includes an automated background scheduler that sends session reminder emails 15 to 1 minutes before a class starts.

In `backend/.env`:
```env
EDUSENSE_SMTP_HOST=smtp.gmail.com
EDUSENSE_SMTP_PORT=587
EDUSENSE_SMTP_USER=edusense.eg@gmail.com
EDUSENSE_SMTP_PASSWORD=your-16-character-app-password
```
*(Generate an App Password via Google Account → Security → 2-Step Verification → App Passwords).*

---

## 📁 Project Architecture

```text
frontend/     React + Vite frontend, interactive dashboards, webcam capture
backend/      FastAPI REST backend, PostgreSQL / SQLite ORM, JWT auth
  app/
    agents/   7 Specialized AI agents + EduSenseAgentWorkflow orchestrator
    api/      REST API route definitions (auth, sessions, AI tools, reports)
    core/     Settings, scheduler, security
    services/ Gemini API client, Ollama runner, PDF/Word/PPTX export services
docs/         Architecture blueprints and workflow flowcharts
```

---

## 👨‍💻 Author & Contact

Developed by **[Adel Mohamed Noufal](https://github.com/adel-noufal)**  
GitHub: [https://github.com/adel-noufal](https://github.com/adel-noufal)  
Repository: [https://github.com/adel-noufal/Edusense](https://github.com/adel-noufal/Edusense)