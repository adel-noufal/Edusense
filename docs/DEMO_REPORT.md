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
