# Changelog

All notable changes to **EduSense** are documented here.

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
