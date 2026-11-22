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
