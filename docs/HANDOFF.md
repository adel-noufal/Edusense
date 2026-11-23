# EduSense — Engineering Handoff

Last updated: 2026-11-22 · Branch: `feature/sessions-ingestion`

## 1. LLM layer architecture

```
feature code (agents, API, RAG, video)
        │
        ▼
app/services/llm.py :: chat(task_type=...)
        │  candidates(task_type)  ── per-feature chain from DEFAULT_FEATURE_CHAINS
        │        │                    (or EDUSENSE_LLM_CHAIN_<TASK> override)
        │        ├─ live /models intersection (discover_models, cached 10 min)
        │        ├─ 1-token probe result per provider/model (probe_all_models, startup)
        │        ├─ per-key daily counter vs 80 % of the documented free RPD
        │        └─ Ollama models appended last, fast-first order
        ▼
circuit breaker (max 4 cloud/local attempts + local fallback)
        ▼
_call_provider → Gemini generateContent | OpenAI-compatible chat/completions
        ▼
mark_success / mark_failure
   • 429 → cooldown from Retry-After (or exponential backoff)
   • 404/410 → disabled_until = now + 6 h, then re-verified via /models
   • never permanent for the process; Ollama is never disabled by a 404
```

Key settings: `ALLOW_PAID_MODELS=false` (default), `KB_ENGINE=auto|private|cloud`,
`EDUSENSE_LLM_CHAIN_<TASK>` for an explicit chain, `EDUSENSE_OLLAMA_URL`.

## 2. Routing table (code defaults, before live discovery)

| Feature | 1st | 2nd | 3rd | 4th+ | Notes |
|---|---|---|---|---|---|
| `prompt_enhance` | groq | nvidia | openrouter | cerebras, deepinfra, gemini, **ollama** | short, latency-first |
| `kb_chat` | groq | nvidia | openrouter | cerebras, deepinfra, gemini, **ollama** | strict grounding, local embeddings |
| `flashcards` | groq | nvidia | openrouter | cerebras, deepinfra, gemini, **ollama** | JSON |
| `quizzes` / `exams` | nvidia | groq | openrouter | cerebras, deepinfra, gemini, **ollama** | strict JSON |
| `recommendations` | groq | nvidia | openrouter | cerebras, deepinfra, gemini, **ollama** | |
| `question_bank` | groq | cerebras | nvidia | openrouter, deepinfra, gemini, **ollama** | bulk |
| `video_script` | gemini | nvidia | openrouter | groq, deepinfra, cerebras, **ollama** | long context/output |
| `reports` | gemini | nvidia | groq | openrouter, deepinfra, cerebras, **ollama** | long, deterministic |
| `general` | groq | nvidia | openrouter | cerebras, deepinfra, gemini, **ollama** | |

Ollama ordering inside the local tier (`_ollama_order`): llama3.2 → llama3.1 → qwen2.5 →
mistral for short/chat work, llama3.1 first for quizzes/exams, mistral first for long scripts.

Live chains (after startup probing) are printed by `GET /api/admin/llm-status`
(field `chains`) and in the doctor.

## 3. Chat surfaces

| Surface | Storage prefix | Retrieval | Endpoint |
|---|---|---|---|
| Knowledge Base chat | `kb:` | uploaded documents only, page-aware | `POST /api/rag/ask` (`engine` optional) |
| AI Chatbot | `web:` | web search + general knowledge + a file attached to that chat | `POST /api/ai/chat` |

Legacy unprefixed conversations are migrated to `web:` on startup
(`migrate_conversation_kinds`); dropping the prefix reverses it.

## 4. How to run and verify

```bat
start-all.bat            :: backend + frontend
verify.bat               :: mojibake scan, imports, pytest --collect-only, frontend build
backend\.venv\Scripts\python.exe scripts\mojibake_scan.py
backend\.venv\Scripts\python.exe -m pytest -m "not live_provider"
backend\.venv\Scripts\python.exe -m app.tools.doctor
```

Live LLM diagnostics: `GET /api/admin/llm-status`, `POST /api/admin/llm-test`.

## 5. Open items (not proven)

- Output-contract compliance suite (language purity, lesson detail ranges, style structure,
  quiz Bloom mapping + second-model answer-key check, flashcard formats, citations).
- Video: Notes field still pre-filled; `video-7` state; real 1-minute MP4 with Gemini disabled.
- Video V2 milestones (scene library, motion lint, TTS word timestamps, contact sheet).
- `verify.bat` end-to-end run, pre-push hook proof, CI result.
- Login flows in a browser: wrong password, unknown user, backend down, session across a
  backend restart.
- 30-request per-feature burst with cache off; Retry-After and 80 % budget observed live.

## 6. Known limits

- Several cloud models on the current keys return 404/410 (Groq model access, NVIDIA
  end-of-life, OpenRouter `:free` removals). The router now degrades to the models that do
  answer plus local Ollama instead of failing.
- Local Ollama on this machine is CPU-bound: 3B models answer short prompts in tens of
  seconds; 70B-class models exceed the request timeout.
- `k`-sized context: Gemini free tier is the only reliable cloud path here, so Gemini share
  is above the design target until working Groq/NVIDIA/OpenRouter keys are available.

## 7. Addendum #12 state (discovery, Ollama boot, contract, video)

### Discovered live models (probe time 2026-11-22 17:37, cache `backend/data/llm_models.json`)

| provider | key | working models (probe latency) | free limits | notes |
|---|---|---|---|---|
| groq | gsk_…Il4D | `allam-2-7b` 334 ms, `qwen/qwen3.8-27b` 264 ms | https://console.groq.com/docs/rate-limits | the former llama-3.x models are refused (404 no access); TTS models need terms acceptance |
| nvidia | nvap…sHS5 | `nvidia/nemotron-3.5-bolt-e4b` 271 ms, `nvidia/riva-translate-4b-instruct-v2` 411 ms | https://build.nvidia.com/ | retired llama-3.3 → 410, cosmos/gemma-3 → 404 function not found |
| nvidia | nvap…vuF9 | same two + `nvidia/ising-calibration-1.5-31b` 436 ms | https://build.nvidia.com/ | second key, same catalogue |
| openrouter | sk-o…1eb2 | `baidu/ernie-5.5-flash-preview:free` | https://openrouter.ai/docs/api-reference/limits | most `:free` slugs answer 429 upstream or empty |
| gemini | AQ.A…SjNg | `gemini-2.5-flash-lite` 641 ms (+ 3.x previews on a 16-token probe) | https://ai.google.dev/gemini-api/docs/rate-limits | key 1 + key 2 share the same free quota group |
| gemini | AQ.A…rahA | `gemini-2.5-flash-lite` 585 ms | same | |
| gemini | AQ.A…drHA | none | same | 2.5-flash and 2.5-flash-lite are 404 "no longer available to new users" |
| deepinfra | sk-d…G9Gy | none | https://deepinfra.com/pricing | every model answers 402: balance required |
| ollama | local | llama3.1, llama3.2, qwen2.5, mistral | https://github.com/ollama/ollama/blob/main/docs/faq.md | CPU-only host |

### Routing rules now in force

- Short features (`prompt_enhance`, `kb_chat`, `flashcards`, `quizzes`, `exams`,
  `recommendations`, `general`, `question_bank`): Groq → NVIDIA → OpenRouter → Gemini → Ollama.
- Long features (`video_script`, `reports`): Gemini first, then the free clouds, Ollama last.
- Empty probe result removes the provider from the chain instead of re-offering configured names.
- Root `EMERGENCY` chain is gone from routing; a provider with zero working models is skipped.
- Local order is language-aware: Arabic → qwen2.5, English short → llama3.2, JSON/quizzes →
  llama3.1, long lessons → mistral.
- `EDUSENSE_DISABLE_CLOUD=1` forces Ollama only; `EDUSENSE_DISABLE_PROVIDERS=gemini` blocks
  one provider (used for the Gemini-off video proof).
- Budget: stop at 80 % of a key's free daily requests, cooldown follows `Retry-After`.

### Ollama boot

`app/tools/ollama_boot.py` checks PATH, `D:\Ollama\ollama.exe`,
`%LOCALAPPDATA%\Programs\Ollama\ollama.exe`, starts `ollama serve` once (no pulls), waits for
`/api/tags`. Called from `launcher.py` before uvicorn, from `doctor.py`, and lazily from the
router. Local calls use the native `/api/chat` with `keep_alive=30m`, `num_ctx` 8192/16384 and
`num_predict` per request; Ollama requests get a 300 s floor instead of 60 s.

### Output contract

`app/services/contract.py` checks lesson detail ranges (Brief 3-4 / Standard 4-6 / Detailed
6-8 sections), language purity, quiz count + 4 options + A-D answer + explanation + Bloom tag
+ answer key, flashcard count/uniqueness/format. `stamp_quiz` adds `bloom` per question and
`answer_key`; every lesson/quiz/flashcard result carries `generated_with`
(language / style / level / provider:model) and the UI renders it.

### Video fixes

- Notes are never pre-filled: retrieval context stays in the prompt; startup reconciliation
  stripped the generated block from 3 legacy projects.
- 4 projects marked `completed` without artifacts were moved to `failed` (no data deleted).
- `video_url` is only returned when `player.html` exists, so no phantom 404 player link.
- `LessonRequest` gained `duration`, so the script word gate uses the requested runtime; short
  videos (±2 min) use a 35 % tolerance instead of 10 %.
- Inline LaTeX is converted to arrows before the player is written.

### verify.bat

New step 8 runs `scripts/verify_extras.py`: starts the backend if it is down, scans recent API
logs for `Traceback`, counts KB documents, ffprobes the newest MP4 (duration > 1 s) and checks
the model dropdown for dead names.

## 8. Still not proven

- Video V2 M1-M4 (feasibility, TTS word timestamps, scene library, motion lint, contact sheet,
  Arabic version, style pacing, render-time report): not started in this addendum.
- CI (GitHub Actions) result: no push happened, so no Actions run exists yet.
- Pre-push hook blocking proof: hook exists; the blocking run was not executed in this session.
- 30-request-per-feature-class burst at full scale: 50 live requests ran (30 enhance, 10 KB,
  5 quiz, 5 flashcards), not 30 per class for every class.
- Ollama timing targets: quiz 108.5 s (target < 45 s), flashcards 37.1 s (target < 30 s), chat
  first token measured only through the streaming path; the CPU host is the limit.
- Second-model answer-key verification: not implemented; the answer key is computed from the
  generated `answer` fields.
- No screenshot of the Arabic submission flow in this addendum.

## 9. Addendum #13 state (ledger, U1/U2, specs)

Process: `docs/ISSUES.md` is now the ledger (P1). An issue is only `DONE` when a named
test that reproduces the visible symptom runs inside `verify.bat`.

### Batch 1 — closed

| ID | What was wrong | Fix | Test |
|---|---|---|---|
| U1 | Session Resources modal centred in the whole document; Ended list printed every row | `components/Modal.jsx` portal dialog (viewport-centred, scroll lock, Esc/overlay close, focus trap); Ended list 20/page + search + from/to dates, newest first | `tests/walkthrough_addendum13.py::run_u1` |
| U2 | UTC stored naive, browser read it as local (06:19 shown for 08:19) | `services/timefmt.py::iso_z` for every API timestamp; `frontend/src/services/time.js` formats in the browser timezone | `tests/test_addendum13_time_utc.py`, `run_u2` |
| U13 | Launcher bound a random port when `PORT=0`, so `/health` never answered on 8000 | `find_free_port` / `preferred_port` reject `<= 0` | `verify.bat` step 8 |

Live proof of U2: `2026-11-14T21:21:34.153224Z` renders as `Indexed: 14 Nov 2026, 23:21`
in Africa/Cairo (`docs/screenshots/add13-u2-kb-indexed-time.png`).

`verify.bat` gained step 9: it runs the Playwright walkthrough after `verify_extras.py`
has started the servers, and fails on any of its assertions.

### Specs written, implementation not started

- `docs/SPEC_RAG.md` — local RAG (structure-aware chunks, local embeddings + reranker,
  exact-passage mode, grounded local generation, zero LLM calls on page load, evaluation
  targets hit@5 ≥ 85 %, faithfulness ≥ 90 %, refusal ≥ 90 % on negatives).
- `docs/SPEC_VIDEO.md` — editable storyboard of scenes, director pass, per-scene hash
  cache, animated templates + captions, TTS, honest ceiling (illustrated explainer, not
  text-to-video), free-key checklist, milestones M1–M4.

Both are specifications only: U3–U11 stay `OPEN` in the ledger.

### Addendum #12 leftovers landed here

`expand_lesson_sections` now caps the section count to the detail-level upper bound and
logs why it expands. The contract suite still cannot be proven on this host: in
`logs/add13-contract1.log` every cloud model answered 404/503 and `ollama mistral`
timed out at 302 s, so the run never completed. Recorded as H1 `BLOCKED` in the ledger.

## 10. Addendum #13 — batch 2 (decisions answered, U14/U15/U16–U20)

These rows are in `docs/ISSUES.md`; this section records what changed and what was measured.

### Decisions that were applied

- **U14 — lessons have no runtime.** `LessonRequest` no longer has `duration`
  (`extra="ignore"` so an old client posting it still works, value dropped). Lesson
  output has no `duration`; `download.js` no longer prints a default "60 Minutes"; the
  video word gate reads `VideoRequest.duration`. The stale test in
  `test_addendum7_quality.py` was rewritten (accepted-but-dropped + video keeps it).
  This is the only old test that was modified.
- **U11 — reversible archive.** `archived_at` on `sessions`, every listing uses
  `services/session_archive.visible_sessions`. 13 rows archived (ids 2, 22, 29, 35, 40,
  44, 48, 70, 73, 85, 100, 107, 109) after exporting
  `data/backups/sessions-archive-20261123T162542Z.json`. "Test Session" id 1 was kept
  because it has a registration and a resource. Restore with
  `scripts/archive_test_sessions.py --restore <backup>`. No row was deleted.
- **U7 — no re-ingest.** The library never lost a document: `ECU-ITAI-3-04.pdf` = 129
  chunks, resource `resource_9` = 15, both filed under the filename
  `ECU-ITAI-3-04.pdf`. `test_async_guide.pdf` and `notes.txt` were **test fixtures**
  written into the live collection by two API tests minutes earlier (15:22:39Z and
  15:22:55Z). Both were backed up (`data/backups/kb-test-fixtures-20261123T163005Z.json`)
  and removed; tests now use `data/chroma_test` + `edusense_knowledge_test`.

### Batch 2 — closed

| ID | What was wrong | Fix | Test |
|---|---|---|---|
| U14 | Lesson schema carried a duration that contradicted the non-video rule | duration removed; legacy field ignored; output and export drop it | `test_addendum7_quality.py` |
| U15 | 8 full-suite failures | 3 real bugs fixed (missing `iso_z` import in the audit logger, conversation list only listing `web:` ids), 1 stale test rewritten against `llm.chat`, 2 live tests marked + skipped by default (`RUN_LIVE_PROVIDERS=1`, `RUN_LIVE_SERVERS=1`), flashcards kept for U3 | the 7 named tests |
| U16 | Backend died on 8000 with WinError 10048 and moved the frontend to 8001 | exclusive bind probe, netstat parsed in Python, stray project servers stopped via CIM, failed ports never retried, buffered logs fixed | `test_addendum13_launcher_port.py` |
| U17 | Audit logger raised `NameError: iso_z` (batch 1 regression) | import added | `test_addendum11_llm_routing.py`, `test_task14_chat_grounding.py` |
| U18 | A new chat conversation was missing from the list | list excludes only `kb:` threads | `test_task8_chatbot_overhaul.py` |
| U19 | "Several minutes" before `/health` answered; no warming-up state | root cause was 12 stray servers; measured cold start **22.3 s** on 8000 with one server; `/health` now returns `warmup.tasks` (`pending/warming/ready/failed`); `PORT=0` is inherited process env only, launcher ignores it | `test_addendum13_health_warmup.py` |
| U20 | Lesson call failed on every provider | cloud JSON was truncated by a token cap, local had a hard-coded 90 s timeout (≈250 tokens at the measured 2.8 tokens/s), and the prompt demanded ~1,600–2,500 output tokens; `except Exception: pass` hid all three behind the template | `scripts/lesson_provider_diagnostic.py` + `logs/add13-lesson-diagnostic.log` |

### Measured lesson run after the fix (U20)

```
[LLM] feature=lesson provider=gemini model=gemini-2.5-flash-lite latency=6.18s outcome=SUCCESS
[contract] expanding Standard: 5 sections (2 thin) -> target 5
[contract] expansion returned 5 sections
WALL_SECONDS 79.0
SECTIONS 5 words_per_section [111, 100, 100, 102, 98]
```

The per-provider errors before the fix (same script): Gemini `200` + unparseable
(truncated) JSON → `INVALID_RESPONSE`; `ollama mistral` timed out; the retry to
`llama3.2` timed out; the agent then answered from the "Expert Fallback Template"
(3 sections, 29–31 words each).

### Gate (batch 2)

The first two end-to-end `verify.bat` runs failed **in the script**, not in the app:

- step 5 reported three `AIzaSy…` strings in `backend/tests/` as leaked keys — the
  exclusion was `:!backend/test_*`, which never matches `backend/tests/`; the values
  are masking-test placeholders. Step 5 now also excludes `:!backend/tests/*`. The
  ledger row describing this then tripped the same scan, so the row describes the
  placeholders instead of quoting them (U22).
- step 2 printed no pass/fail summary: `verify.bat` passed `-q` while
  `backend/pytest.ini` already sets `-q`, which pytest 9 reads as `-qq` and suppresses
  the summary. The duplicate flag is gone (U22).
- step 8 failed on a traceback from `logs/api-add13c.log`, a server stopped long before
  the run (the U17 `iso_z` crash, already fixed). The window is now 60 minutes and the
  line reports how many older logs were not inspected (U23).

`logs/add13-verify-gate3.log`, full run, exit 0:

```
[1/5] DOCTOR RESULT: ALL SYSTEM CHECKS PASSED [OK]
[2/5] 132 passed, 30 skipped, 3 deselected, 1 warning in 253.26s (0:04:13)
[3/5] LAYOUT PASS 1366x768 /student ... 390x844 /student   (13 passes)
[4/5] ✓ built in 9.76s
[5/5] credential scan: no matches
[6/9] FILES=0 LINES=0
[7/9] collection OK
[8/9] [OK] no Traceback in API logs of the last 60 min (21 older log(s) not inspected)
      [OK] KB documents: 2   [OK] ffprobe video-99999.mp4: 20.0s, 27 KB
      [OK] dropdown: 12 models, ollama_running=True
      VERIFY EXTRAS PASSED
[9/9] PASS U1 modal is inside the viewport / does not scroll / body locked / Esc
      PASS U1 search filters the ended list
      PASS U2 knowledge base shows Cairo time for the ingested_at instant
      FAILURES: []
VERIFY PASSED
EXIT=0
```

Cold start with the new launcher and warm-up code, measured on the same machine:
`HEALTH_200 after 35s` (`logs/add13-verify-api.log`, `/health` returning
`warmup: {model_discovery: ready, knowledge_base: warming, emotion_detector: pending}`).
Earlier measurement on an idle machine was 22.3 s; both are inside the 60 s target.

### Still open

U3 (remaining fabricated fallbacks, canonical JSON, renderers, filler judge,
flashcards), U4–U6, U8–U10, U12. The gate is green; nothing is pushed yet.
