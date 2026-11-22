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
