# Architecture

```mermaid
flowchart LR
  Student[Student Browser] --> Frontend[React + Vite]
  Instructor[Instructor Browser] --> Frontend
  Frontend --> API[FastAPI REST API]
  API --> Auth[JWT + Password Hashing]
  API --> DB[(SQLite)]
  API --> Agents[Google ADK Multi-Agent Layer]
  Agents --> Emotion[Emotion Analysis Agent + DeepFace]
  Agents --> Engagement[Student Engagement Agent]
  Agents --> Recs[Recommendation Agent]
  Agents --> Lesson[Lesson Generation Agent]
  Agents --> Quiz[Quiz Generation Agent]
  Agents --> Report[Report Generation Agent]
  API --> Video[FFmpeg Video Service]
  Report --> PDF[PDF Reports]
  Video --> MP4[Generated MP4]
```

## Tables

- users
- profiles
- sessions
- session_registrations
- emotion_logs
- reports
- feedback
- video_projects
- quizzes

## Production Hardening Checklist

- Replace development secret key.
- Configure HTTPS behind a reverse proxy.
- Add database migrations with Alembic.
- Add background workers for heavy DeepFace and FFmpeg jobs.
- Store generated files outside the app package in production.
- Add rate limits to auth and webcam ingestion endpoints.
