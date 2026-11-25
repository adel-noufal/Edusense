# EduSense — User Guide

This guide covers the installed application. Accounts below exist **only in this local
installation** and are created by the first database seed. They are not production
credentials: change them (or set `DISABLE_DEFAULT_ACCOUNTS=true` in `backend/.env`)
before exposing the app to a network.

## Local demo accounts

| Role | Email | Password |
|---|---|---|
| Instructor | `instructor@edusense.local` | `Password123` |
| Student | `student@edusense.local` | `Password123` |

Admins use the same sign-in form with an admin account created by the seed.

## Start and stop

1. Double-click `start-all.bat` in the project folder.
2. Wait until the browser opens <http://localhost:5173>.
3. To stop, close the **EduSense API** and **EduSense Frontend** windows.

If the API window shows `Port 8000 is still in use by PID …`, stop that process (the
window names it) and run `start-all.bat` again. The API never moves to another port on
its own.

## Instructor walkthrough

1. **Dashboard** — live/upcoming sessions, quick stats. **Run Feedback Loop** analyses
   ended sessions; **Select all** selects every listed session (“N of N”).
2. **Sessions** — create a session (title, date, time, duration), edit it, **Start**
   (15-minute preparation room) and **End**. Ended sessions are read-only.
   The resources button shows files tagged to the session.
3. **Sources** — upload PDFs/notes, optionally tag them to sessions. Students then see
   them under **My Resources**.
4. **Knowledge Base** — upload a book, ask a question, or paste a passage. Answers cite
   page numbers/sections. Opening the page performs no LLM call.
5. **AI Lessons / Quizzes / Flashcards / Videos** — pick sources, topic, language
   (English/Arabic) and model, then generate. Downloads (DOCX/PPTX/PDF) are created
   server-side from the same stored content you see on screen.
6. **Quizzes** — publish as an exam with a deadline; students see it under **Exams**.
7. **Reports** — choose a session to see attendance, emotion samples, distribution and
   engagement. **CSV** downloads UTF-8 with BOM (Excel-safe); **PDF** is a full report.

## Student walkthrough

1. **Dashboard** — enrolled/upcoming/completed counts and the **Emotion Recognition Trial**.
2. **Emotion trial** — press **Start Camera**, accept the consent dialog, and face the
   camera. The badge shows *starting camera → no face → too dark → reading → result*
   with a confidence bar and the top three emotions. Everything is computed in the
   browser; no frame is uploaded. **Stop camera** releases the device.
3. **Browse / Upcoming** — enroll in a session; **Upcoming** lists your registrations.
4. **Live session** — when the instructor goes live, open the session and press
   **Turn camera on**. The instructor sees your attendance and emotion distribution;
   your own panel shows the current label and confidence.
5. **Exams** — open a published exam, answer, submit, and read the result view.
6. **Assignments** — upload a file and see the instructor's grade/feedback.
7. **Profile** — change name/password/language and manage camera consents
   (emotion detection and quiz anti-cheat are separate).

## Camera troubleshooting

| Badge / message | Meaning | What to do |
|---|---|---|
| “Camera permission was denied” | Browser blocked the camera | Padlock icon → allow camera → **Retry camera** |
| “The camera is already in use” | Another app/tab owns it | Close the other app (Teams, Zoom, another EduSense tab) and retry |
| “No camera was found” | No device detected | Connect a webcam; check Windows → Privacy → Camera |
| “No face detected” | Face not visible/large enough | Move closer, centre your face in the guide |
| “Too dark” | Frame brightness below the threshold | Add light in front of you, avoid backlight |
| “Reading your expression…” | Confidence too low / two emotions close | Hold still for a second; the result stabilises |

The model files live in `frontend/public/models` and are served by the app, so the
feature works without internet access.

## Data and privacy

- Camera frames never leave the browser. Only `{emotion, confidence, timestamp}` is stored.
- Emotion detection and quiz camera monitoring require separate consents, revocable in
  **Profile**.
- Uploaded files, the vector index and the database stay on this machine
  (`backend/app/static/resources`, `backend/data/chroma`, the SQLite file).
- Amount of emotion data needed for a session analysis: at least 3 samples and
  30 seconds of attendance (configurable in `backend/.env`).
