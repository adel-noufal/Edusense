# EduSense — Live Demo Guide

> A walkthrough of every major feature in the EduSense AI Education Platform.

---

## 🚀 Quick Start (30 seconds)

```bash
# 1. Clone & install
git clone https://github.com/adel-noufal/Edusense.git
cd "Edusense 2"

# 2. Start backend (auto-seeds DB with demo accounts)
start-backend.bat

# 3. Start frontend
start-frontend.bat

# 4. Open in browser
start http://localhost:5173
```

**Demo Accounts (auto-seeded):**

| Role       | Email                          | Password   |
|------------|-------------------------------|------------|
| Instructor | `instructor@edusense.com`     | `demo1234` |
| Student    | `student@edusense.com`        | `demo1234` |

---

## 🎥 Feature Walkthrough

### 1. Instructor Dashboard

Log in as instructor → you'll see your live stats: sessions created, students enrolled, engagement score, and videos generated.

**What to try:**
- Click **"Run Feedback Loop"** → watch the AI agent analyze emotion data and generate adaptive teaching recommendations
- Check the **Attention Timeline** chart showing focus trends over time

---

### 2. AI Lesson Generator

`Instructor → AI Lessons`

- Enter any topic (e.g., *"Quantum Computing for Beginners"*)
- Choose language, teaching style, and difficulty
- Hit **Generate** → Gemini 2.0 Flash builds:
  - Learning objectives
  - Structured sections with key points
  - Slide-by-slide content
  - A full lesson summary
- Export as **Markdown**, **HTML**, or **ZIP package**

---

### 3. Quiz Generator

`Instructor → Quizzes`

- Enter a topic and difficulty → get 5–20 MCQs with explanations
- Quizzes are **saved to the database** and linked to sessions
- Students can take quizzes live during sessions

---

### 4. Flashcard Generator

`Instructor → Flashcards`

- Generate study cards from any topic instantly
- **Flip animation** on each card (front → back reveal)
- Export as **JSON** or printable **HTML**

---

### 5. AI Video Generator

`Instructor → Videos`

- Describe a lesson topic and duration
- The backend generates:
  - Scene-by-scene slide content
  - MP3 narration audio (via gTTS)
  - An interactive slide player (auto-advances with audio)
- Export as **MP4** (requires FFmpeg) or **MP3**

---

### 6. Live Classroom

`Instructor → Sessions → Create → Start`

**Instructor flow:**
1. Create a session with title, date, and max students
2. Click **Start** → enter the Live Room
3. Click **Share Screen** → students see your screen in real time (WebRTC)
4. Monitor the **Student Emotion Panel** on the right: angry, happy, focused, confused, etc.

**Student flow:**
1. Browse and join the session
2. Enable webcam → emotions are analyzed every 1.5s using the PyTorch v7 EfficientNet-B0 model
3. Data is sent to the backend and stored as `emotion_logs`

---

### 7. Emotion Detection (PyTorch v7)

The webcam feed is processed locally via the FastAPI backend:

- **Model:** EfficientNet-B0 fine-tuned on FER2013+ augmented dataset
- **Accuracy:** 90.9% (7-class: angry, disgust, fear, happy, neutral, sad, surprise)
- **Rate limit:** 1 frame per 1.5 seconds per user (prevents spam)
- **Fallback:** DeepFace if PyTorch model not available

---

### 8. Analytics & Reports

`Instructor → Reports`

- Per-session emotion distribution (pie / bar charts)
- Engagement score calculation
- **Export PDF** — ReportLab-generated executive report with:
  - Session summary
  - Emotion breakdown table
  - Engagement trend graph

---

### 9. Database Preview

`Instructor → Database`

Live read-only view of all tables:
- `users`, `sessions`, `emotion_logs`, `quizzes`, `reports`, `video_projects`, etc.
- Shows row count + paginated preview
- Works with both **SQLite** (local) and **PostgreSQL** (production)

---

### 10. Language Toggle (Arabic / English)

- Click **العربية** in the top-right corner → entire UI switches to RTL Arabic
- All pages, forms, and labels are fully translated

---

## 🧪 API Playground

Once the backend is running, visit:

```
http://localhost:8000/docs
```

This is the interactive **Swagger UI** — you can test every endpoint:
- Authenticate with the demo credentials
- Call `/api/emotions/analyze` with a base64 image
- Generate lessons, quizzes, and reports directly

---

## 🐳 Docker Dev Setup

```bash
docker-compose -f docker-compose.dev.yml up --build
```

This starts:
- PostgreSQL 16 (port 5432)
- FastAPI backend with hot-reload (port 8000)
- Vite frontend with HMR (port 5173)

---

## 📊 Architecture at a Glance

```
Browser (React + Vite)
    │
    ▼
FastAPI Backend (Python 3.13)
    ├── Auth: JWT + bcrypt
    ├── Emotions: PyTorch EfficientNet-B0 v7
    ├── AI: Google Gemini 2.0 Flash / Ollama fallback
    ├── Reports: ReportLab PDF generation
    └── Scheduler: APScheduler (session reminders)
    │
    ▼
PostgreSQL / SQLite (SQLAlchemy + Alembic migrations)
```

---

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to run tests, submit PRs, and report bugs.
