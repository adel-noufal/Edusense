# Demo-day readiness report — 2026-11-24

Branch `feature/sessions-ingestion`, tag `demo-base` at `4db15aa` before any
demo-day change. Nothing was pushed to `main`.

Legend: **GREEN** = walked in a real browser today or proven by a named test
whose output I pasted. **YELLOW** = works but only proven by automated tests, not
clicked today, or a known gap. **RED** = broken or not verified.

## Feature walkthrough (Step 1, real browser, instructor login)

| Feature | Status | Evidence |
|---|---|---|
| Login (instructor) | GREEN | Logged in at 05:46 with `instructor@edusense.local`; landed on `/instructor`. `docs/screenshots/demo-01-dashboard.png` — a teal "Hello, Adel" banner, Managed Sessions list with *Ai* / *Task 2 Duration Accuracy Test Session* / *Task 9 Quantum Computing* / *Task 5 Linear Algebra Session*, all marked **Ended**, a **Run Feedback Loop** button and an empty "Improvement Recommendations" panel. |
| Dashboard + Run Feedback Loop | GREEN (render) / YELLOW (loop result) | Button present and enabled; the loop itself was not executed in this sitting (it calls providers, ~20–40 s). |
| Sessions (Upcoming / Ended, resources modal) | YELLOW | Ended sessions render on the dashboard; the resources modal was not opened today. |
| Sources page | YELLOW | Not opened today; unchanged by this batch. |
| Knowledge Base library | GREEN | `/instructor/knowledge-base` shows **2 documents**: `ECU-ITAI-3-04.pdf` and `resource_9` — exactly the U7 baseline (144 chunks). Screenshot `demo-02-kb-library.png`. |
| Knowledge Base chat | GREEN | Asked "How is model drift detected in the book?" with the **Private (Ollama)** engine. Answer returned in ~15 s, cited **ECU-ITAI-3-04.pdf p.128**, and the footer said **GROUNDED IN 1 DOCUMENT CHUNK**. The suggestion chips are now generated from the library (`Summarise the key points of ECU-ITAI-3-04.pdf`) instead of the old Calvin-cycle / Newton / biology chips. |
| AI Chatbot (web) | YELLOW | Not exercised today; web answers remain separately labelled. |
| AI Lessons EN + downloads | GREEN (generation) / YELLOW (download) | `scripts/f1_acceptance.py` against an API with **Gemini disabled**: lesson EN 200 in 26.3 s, 5 sections, 3/3 topic keywords, 0 banned filler phrases. DOCX/PPTX export not re-checked today (F7 below). |
| AI Lessons AR | GREEN (generation) | Same run: 200 in 27.3 s, 5 sections, Arabic overview, 2/2 keywords, 0 filler. |
| Quizzes + student exam | GREEN | F5 contract test: violation JSON body → 200, attempt locked; `tests/test_section5_quiz_publishing.py` 20/20 and `tests/test_task10_11_quiz.py` green in the same run (26 passed together). |
| Flashcards | YELLOW | Live: 200 in 3.4 s, on-topic Photosynthesis cards, no fabricated "web title" fronts — but a request for 8 returned **5** real cards. Honest under-count instead of invention. |
| Videos | YELLOW | Pre-generated `video-14.mp4` (61 s, h264 1280×720 + aac) plays; scene density and citation stripping fixed in code and covered by `tests/test_addendum13_video_scenes.py`, but **no new video was rendered** after the change. |
| Reports + CSV | YELLOW | Not opened today. |
| Student emotion trial | RED (unverified) | Not exercised today; F4 below was not implemented. |
| Offline mode | YELLOW | Local Ollama is up with 4 models; engine defaults to Private, but a full offline walkthrough was not run. |

## Provider status (live probe, `scripts/llm_diagnostic.py --test-all`)

| Provider | Keys | Status |
|---|---|---|
| Groq | 1 | HEALTHY (`allam-2-7b`, `qwen/qwen3.8-27b`) |
| NVIDIA | 2 | HEALTHY (`nvidia/nemotron-3.5-bolt-e4b`) |
| OpenRouter | 1 | HEALTHY (`:free` slugs only) |
| Gemini | 3 | configured, **free quota exhausted for demo day — do not burn** |
| Ollama | local | HEALTHY, 4 models |

Ollama speed measured on this machine (60-token answer, cold-ish):

| Model | tok/s | Note |
|---|---|---|
| `llama3.2:latest` | **13.07** | fastest — use for short answers / KB default |
| `mistral:latest` | 1.50 | |
| `qwen2.5:latest` | 1.36 | better Arabic |
| `llama3.1:latest` | 1.18 | |

**Fastest local model for short answers: `llama3.2` (≈9× the next model).**

## Fixed in this batch (with proof)

| ID | Fix | Proof |
|---|---|---|
| F1 | Every content-fabricating fallback deleted (`lesson_agent`, `quiz_agent`, `flashcard_agent`, `base.LocalLLM._template`, orchestrator, KB). Total provider failure now raises `ContentGenerationUnavailable` → HTTP 503 `{code: providers_unavailable, retry: true}`. Specialist models (`riva-translate`, `ising-calibration`, `embed`, `guard`, `tts`, `vision`, `-preview`) are excluded from every chain. | `logs/f1-acceptance2.log`: 4/4 PASS with Gemini disabled. `tests/test_task6_flashcard_distinctness.py` rewritten (8 passed with `test_addendum7_quality.py`). |
| F3 (part) | KB engine defaults to **Private** (local Ollama); suggestion chips come from the library; inline `[Source: …]` / `[Web N: …]` markers stripped from prose (`strip_inline_citations`). | Live answer above; `config.py` default `private`. |
| F5 | Exam violations 422 caused by body-vs-query mismatch; endpoint now accepts both, and `details` is returned parsed. | `tests/test_addendum13_exam_violation_contract.py` (3 tests) + the two existing quiz suites. |
| F6 (a,b) | One scene per ~10 s (1-minute video → 6 scenes, was 2×30 s); citations and URLs stripped from slide text, narration and bullets. | `tests/test_addendum13_video_scenes.py` (4 passed). |
| F2 (part) | Specialist/non-chat models filtered out of routing and discovery (`LLMRouter.is_chat_model`). Grouped dropdown + badges: **not done**. | code + diagnostic chains no longer list specialist models. |

## Not done (say "not done" if asked)

- **F4 emotion trial**: contrast badge, warm-up state, brightness gate — untouched.
- **F7 lesson exports**: one JSON rendered by screen/DOCX/PPTX/PDF — untouched. The
  exports still build independently, so titles may drift between formats.
- **F6 (c,d)**: real SVG diagrams and per-scene regenerate — untouched. The video
  is a slideshow renderer; call it "basic mode".
- **F2**: the dropdown itself (optgroups, Free/Fast/Arabic/Offline badges, status
  dot, "Generated with <model>") — server-side filtering only.
- **Flashcards exact count** when the model returns fewer cards.
- **Playwright recording** of the demo script (Step 3.5) — not run.

---

## Final push — 2026-11-25 06:19 → 06:58 (40-minute window, real results only)

### What this session actually produced

| Item | Status | Evidence |
|---|---|---|
| Demo content pack script (`scripts/demo_pack.py`) | written, **not yet proven end-to-end** | the first run stalled because the API process on port 8000 died (`error while attempting to bind … 10048`) after a bind conflict; `docs/demo-pack/` is still empty |
| Chained runner (`scripts/run-demo-pack.sh`) | written, launched | regenerates the API on 8000 if absent, then runs the pack, then the 60 s video; output in `logs/demo-pack.log`, `logs/demo-video.log`, `logs/run-pack.out` |
| Flashcard exact count (8 asked, 5 returned) | **partially addressed** | `scripts/demo_pack.py` asks again only for the missing cards (`count = missing + 2`), merges, deduplicates by front text, caps at 8, and records `requested / rounds / counts`. It never invents a card. The agent still falls back to `PEDAGOGICAL_DIMENSIONS` filler when `real_sources_only=False` (route at `backend/app/api/ai.py:552` does not pass the flag) — **this remains a fabrication risk to disable** |
| Video 6-scene render + ffprobe + contact sheet | **NOT DONE** | `/tmp/mkvideo.py` was launched; no MP4/probe exists yet |
| Emotion (task 4) | **NOT STARTED** | untouched |
| Lesson exports consistency (task 5) | **NOT DONE** | `POST /api/ai/lessons/export-pptx` calls `lessons.generate()` again, so a DOCX/PPTX export is a *second* generation and can differ from the lesson on screen. `POST /api/ai/export/{pptx,docx,pdf}` take a stored `content` dict and are the consistent path — the UI still uses the regenerating route |
| YELLOW feature sweep (task 6) | **NOT DONE** | Sessions modal, Sources, Reports+CSV, Feedback Loop, student Upcoming/History, offline chat not exercised today |
| Ollama default model (task 7) | **partially verified** | `backend/app/core/config.py:106-110`: `ollama_model=llama3.2`, but `ollama_model_lesson=mistral`, `ollama_model_quiz=llama3.1` — the two slowest models are still the defaults for lessons and quizzes. GPU: Quadro P2000, **4096 MiB total**; the 8B models are 4.9 GB (llama3.1) and 4.4 GB (qwen2.5) and cannot fit, so they run on CPU — that is why they measure 1.2–1.5 tok/s while the 3B `llama3.2` fits and reaches 13.07 tok/s |
| Rehearsal twice with recording (task 8) | **NOT DONE** | `docs/DEMO_SCRIPT.md` untimed, no `.webm` |
| `docs/DEMO_REPORT.md` update | **this section** | honest status above |
| Tag `demo-final`, full verify, push | **NOT DONE** | tagging or pushing without a green gate would misrepresent the tree; the last green gate is still `logs/demo-gate2.log` (`139 passed, 30 skipped`) on commit `a5c3f30` / tag `demo-ready` |

### Why the window closed early

The 40-minute budget was spent re-establishing a running API. `netstat` showed nothing on 8000 at 06:19, a health check then returned 200, my own uvicorn copy failed with `10048`, and by 06:50 the port answered `000` — two processes had been fighting for the port. Generation itself was never at fault: the pack script and the video script were both blocked on a dead socket, not on an LLM call.

### What is safe to show tomorrow

Only what was proven before this window: login, dashboard, KB library, KB chat, lesson/quiz/flashcard generation with Gemini disabled (`logs/f1-acceptance2.log`), exam-violation contract, video-scene density by unit test, and the gate at `a5c3f30`. Everything in the list marked NOT DONE above must be presented as "not shown" rather than demonstrated live.

---

## Final push — measured results (25 Nov, 06:19–07:00)

The first `docs/DEMO_REPORT.md` section above was written before generation ran. This section replaces its "not done" rows with what actually happened.

### 1. Demo content pack — 7 of 8 items stored and real

All items were generated through the live API on `127.0.0.1:8000` with `EDUSENSE_DISABLE_PROVIDERS=gemini` (Gemini was never called). Stored JSON in `docs/demo-pack/`, produced by `scripts/demo_pack.py`:

| Item | Stored id | Result (`docs/demo-pack/…`) |
|---|---|---|
| Lesson EN "Neural Networks" | `AIGeneration` 107 (`topic` = "Mastering Neural Networks") | 5 sections, real headings: Foundations of Neural Networks · The Forward Propagation Process · Learning and Error Correction · Real-World Application: Image Classification · Practical Implementation Insight (`lesson-en.json`) |
| Lesson AR | `AIGeneration` 106/105 | Topic "إتقان الشبكات العصبية…", 5 sections, body text is Arabic (`lesson-ar.json`) |
| Quiz → published exam | `Quiz` 149 "Neural Networks Master Assessment" | 5 questions, 4 options each, `is_exam=True`, `is_published=True`, `session_id=19` (`quiz.json`, `quiz-exam.json`) |
| Flashcards | `AIGeneration` 108 | **8 of 8 in one call** (`rounds=1`, `counts=[8]`) — every front is a distinct on-topic NN question (`flashcards.json`) |
| KB Q&A 1 (normal) | `kb-q1-normal.json` | 644-char grounded answer, 5 sources incl. pages 55, 1, 51, 5, 96 of `ECU-ITAI-3-04.pdf` |
| KB Q&A 2 (pasted passage) | `kb-q2-passage.json` | 1865-char answer explaining the Alibi Detect drift pipeline, 5 sources (pages 54, 5, 44, 41, 1) |
| KB Q&A 3 ("page 58") | `kb-q3-page.json` | **RED** — the scope guardrail refuses: "Page numbers in documents are not typically considered part of the educational content." Sources 57/58/59 were retrieved, so retrieval works and the guardrail blocks the answer |
| Web-chat answer | `webchat.json` | 904 chars on backpropagation, `mode=online_web_only`, `web_results_used=3`, provider `ollama`/`llama3.2:latest` — but **`sources=[]` and no `[n]` markers in the answer**, so the numbered-citation requirement is **not met** |

**Exam visibility was broken and is now proven working.** Publishing to session 3 returned 200 but the student never saw the exam: the student has no `SessionRegistration` for session 3, and `/api/sessions/3/join` answers 400 "no longer open for registration" (session is ended). Republishing the same quiz to session 19 — where the student is genuinely registered — made it appear: `student/exams` → `[(149, 'Neural Networks Master Assessment', 19, 'Task 9 Quantum Computing'), (147, 'Midterm: Quantum Gates', 19, …)]`. **Lesson for the demo: publish the exam to a session the student is enrolled in, not just to "a session".**

### 2. Flashcard count — GREEN

The API returned 8 cards for `count=8` in a single round with no duplicates; `scripts/demo_pack.py` only refills when a response under-delivers (it asks for `missing + 2` and deduplicates by front text). The fabricated `PEDAGOGICAL_DIMENSIONS` padding path still exists for `real_sources_only=False` and is **never reached** when the model delivers, but it should be deleted: `backend/app/api/ai.py:552` does not pass the flag.

### 3. Video — NOT DONE

`scripts/mk-demo-video.py` (60-minute-fresh, duration 60 s, Gemini disabled) produced no output in `logs/demo-video.log` and no new `.mp4` in `backend/` within the window; the request was still blocked when the window closed. **No new video exists, no ffprobe, no contact sheet.** The 6-scene change remains proven only by `tests/test_addendum13_video_scenes.py`.

### 4. Emotion — RED

`backend/tests/fixtures/faces/` did not exist; three fixtures were created (`smile-generated.jpg` — a generated frontal smiling portrait, `too-dark.jpg` — the same frame at 7 % brightness, `no-face-wall.jpg` — a blank wall gradient) and `scripts/emotion_fixture_check.py` posts them to the real `POST /api/emotions/analyze-trial` as the demo student after granting `emotion_detection` consent:

```
consent: 200
smile-generated.jpg    200 79.86s {"emotion": null, "confidence": 0.0, "face_detected": false, "hint": "timeout", "backend": "fallback"}
too-dark.jpg           200  6.02s {"emotion": null, "confidence": 0.0, "face_detected": false, "hint": "timeout", "backend": "fallback"}
no-face-wall.jpg       200  2.82s {"emotion": null, "confidence": 0.0, "face_detected": false, "hint": "no_face",  "backend": "fallback"}
garbage-bytes          200       {"emotion": null, "confidence": 0.0, "face_detected": false, "hint": "bad_image","backend": "fallback"}
```

A smiling face returns **no emotion at all** — the detector times out and reports `backend: "fallback"`. The "3-second guard" inside the endpoint also did not bound the request: the smiling frame took 79.86 s wall-clock. The four hints (`timeout`, `timeout`, `no_face`, `bad_image`) are at least distinct, but "too dark" cannot be distinguished from "detector too slow", and no confidence badge can be shown because nothing is ever detected. **Do not demo emotion detection.**

### 5. Lesson exports — NOT DONE

`POST /api/ai/lessons/export-pptx` / `export-word` call `lessons.generate()` a second time, so the exported deck is a *different* generation from the lesson on screen. The consistent path (`POST /api/ai/export/{pptx,docx,pdf}` with a stored `content` dict) exists but the UI does not use it. No LibreOffice render was produced.

### 6. YELLOW sweep — NOT DONE

Sessions modal, Sources, Reports + CSV BOM, Feedback Loop Select All, student Upcoming/History and the llama3.2-only offline chat were not exercised in a browser in this window.

### 7. Ollama — measured, and the 1.3 tok/s question answered

`ollama ps` while generating shows `llama3.2:latest` with `size_vram=2 397 600 481` of `size=3 409 014 946` — i.e. **the GPU is used**, about 70 % of the model in VRAM on a Quadro P2000 with **4 096 MiB** total. `llama3.1` (4.9 GB) and `qwen2.5` (4.4 GB) do not fit in 4 GB, so they run on CPU, which is exactly why they measure 1.2–1.5 tok/s while llama3.2 reaches 13 tok/s. Config defaults still point lessons at `mistral` and quizzes at `llama3.1` (`backend/app/core/config.py:108-109`) — those must be switched to `llama3.2` before any offline demo, or a quiz will take minutes.

### 8. Rehearsal — NOT DONE

No timed rehearsal, no `.webm`.

### 9. Gate / tag / push

`logs/demo-gate3.log` holds the gate run of this final tree. Tag `demo-final` and the push are reported in the final message, not assumed here.

### Checked directly against the running API in this window

| Endpoint | Result |
|---|---|
| `GET /api/reports/sessions/19/export.csv` | 200, `text/csv; charset=utf-8`, 889 bytes, **UTF-8 BOM present** (`EF BB BF`) — Excel will open it with correct accents |
| `GET /api/ai/generations` | 200, lists the pack: id 107/106 lesson, 108 flashcard, 97–103 earlier runs |
| `POST /api/sessions/3/join` (student) | 400 "no longer open for registration" — session 3 is ended, so it cannot be used to give the student an exam |
| `GET /api/quizzes/student/exams` (student) | after republishing to session 19: `149 Neural Networks Master Assessment`, `147 Midterm: Quantum Gates` |
| `GET /api/rag/engine` | `private` (Ollama), `may_train_on_data: false`, embeddings local MiniLM |
| `/api/health` under load | returns 200 (the 000s seen mid-run were the port being held by a dead process, not an app failure); uvicorn must be started as a real background process, `nohup … &` inside a one-shot shell leaves the port dead |

### Feature verdict for demo day

- **GREEN, safe to demo with stored items:** lesson generation EN + AR, flashcards (8/8), quiz generation + publish-as-exam (student-visible), KB Q&A on a normal question and on a pasted passage, Reports CSV export (BOM), KB library, KB chat.
- **YELLOW, show stored artefact only, do not generate live:** video (no new render), web chat (answer is real but has no numbered citations), lesson DOCX/PDF/PPTX (export is a second generation).
- **RED, do not show:** emotion detection (never detects a face, times out), "page 58" page-number question (guardrail refuses).
