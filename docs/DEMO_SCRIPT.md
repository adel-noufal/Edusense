# EduSense — 7-minute demo script (demo day)

Everything below was rehearsed on this machine on 2026-11-24. Times are what the
machine actually did, not targets. Log in as **instructor@edusense.local /
Password123** (student: **student@edusense.local / Password123**).

Open with `demo-prepare.bat` (starts backend + frontend, preloads the local
models, waits for `/health`, opens the login page).

| # | Time | Click path | Sample input | Say | If it fails |
|---|---|---|---|---|---|
| 1 | 0:00–0:30 | Login page → instructor | — | "One login, three roles; the instructor account lands on the teaching dashboard." | If login spins: `demo-prepare.bat` again, it re-checks `/health`. |
| 2 | 0:30–1:30 | Dashboard → **Run Feedback Loop** | keep the default session | "Attendance, quiz results and emotion signals are combined into one feedback loop for the session." | Numbers already loaded from the last run are still on screen — read those. |
| 3 | 1:30–2:15 | Sessions → Upcoming / Ended → resources modal | open an Ended session | "Every session keeps its recording, resources and AI outputs; nothing is deleted." | Ended tab is static data; the modal opens locally. |
| 4 | 2:15–3:15 | Sources / Knowledge Base → ask about the book | `What is drift, and how is it detected?` | "Answers come from the uploaded book, with the page number. Local engine by default: no cloud call." | If the model is slow: the same question is in the KB history tab, already answered with its pages. |
| 5 | 3:15–4:00 | AI Chatbot (web search) | `Latest research on retrieval-augmented generation` | "Web answers are labelled separately from course answers." | Show the stored web answer from the content pack. |
| 6 | 4:00–5:00 | AI Lessons → **Generate** → Download | topic `Python variables`, Standard, English | "The lesson is stored once as JSON; the screen view, DOCX and PPTX all render that same JSON." | Use the pre-generated **Lesson EN** in the pack (DOCX/PPTX already rendered). |
| 7 | 5:00–5:45 | Quizzes → student exam | start the published exam, switch tab | "Anti-cheat: the violation is recorded, the attempt locks, the instructor can re-enable." | The violations list in the instructor view already shows the recorded entries. |
| 8 | 5:45–6:20 | Videos | open the pre-generated video | "A 60-second video now has six scenes of ten seconds, with citations stripped from the slides." | The stored MP4 plays from disk; no generation needed. |
| 9 | 6:20–6:45 | Reports → CSV | pick the session | "Reports and CSV come from the same stored data." | CSV is generated locally, no provider involved. |
| 10 | 6:45–7:00 | Student emotion trial | allow the camera | "A clear badge states what the detector sees: no face / too dark / uncertain / happy…" | If the camera is unavailable, the badge says so explicitly — that is the intended state, not an error to hide. |

## Do NOT show live (provider-dependent)

- **Long Detailed lessons** (8 sections): 90–130 s and the free quota is the only
  thing standing between you and a 429.
- **Gemini-only features**: free quota is exhausted for demo day; every demo path
  above runs on Groq / NVIDIA / Ollama.
- **Video generation from scratch**: 60–120 s of script calls plus TTS; play the
  pre-generated MP4 instead.
- **PPTX/DOCX export of a *new* lesson** if you have not rehearsed it — use the
  pack's files (they are verified to match their JSON).

## Fallback rules

1. Any AI screen that fails now shows `503 … Nothing was generated. Press Retry.`
   That message is honest, not a bug — switch to the pre-generated item.
2. Never re-run a generation that just failed twice; move to the stored pack.
3. The pack lives in `docs/demo-pack/` with a `README.md` listing each item,
   its topic, its model and its screenshots.
