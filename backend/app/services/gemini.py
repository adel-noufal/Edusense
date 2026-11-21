"""
gemini.py — Central Gemini client for EduSense.

Single entry point for ALL Gemini text/JSON generation. Every agent and
service must call generate_content / generate_json / generate_json_any —
no direct HTTP calls to the Gemini API elsewhere.

Features:
- Multi-key rotation (GEMINI_API_KEY comma list, GEMINI_API_KEY_N, chatbot key)
- Ordered per-task model fallback chains (GEMINI_MODELS env, per-task overrides)
- Per (key, model) cooldown with exponential backoff + jitter; honors
  Retry-After on 429/503
- Typed GeminiError with machine-readable codes
- Masked-key operational logging (never logs key material)
"""
import json
import logging
import random
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class GeminiError(RuntimeError):
    """Typed error surfaced to callers; `code` is machine-readable."""

    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    AUTH_ERROR = "AUTH_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN = "UNKNOWN"

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.user_message = message


# ---------------------------------------------------------------------------
# Key + model rotation state
# ---------------------------------------------------------------------------

@dataclass
class _PairState:
    failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""


class GeminiRotator:
    """
    Thread-safe rotator over (api_key, model) pairs.

    Ordering: for each model in the task chain (in order), try every key
    round-robin. A pair that fails with a rotatable error is cooled down;
    pairs are retried after cooldown with exponential backoff.
    """

    BASE_BACKOFF = 30.0      # seconds; doubles per consecutive failure
    MAX_BACKOFF = 900.0
    COOLDOWN_JITTER = 0.25   # ±25%

    def __init__(self):
        self._lock = threading.Lock()
        self._key_index = 0
        self._states: dict[tuple[int, str], _PairState] = {}

    # -- key helpers ------------------------------------------------------

    @staticmethod
    def mask_key(key: str) -> str:
        if not key or len(key) < 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    def get_keys(self) -> list[str]:
        return get_settings().gemini_api_keys

    # -- model chains -----------------------------------------------------

    @staticmethod
    def _parse_chain(raw: str) -> list[str]:
        return [m.strip() for m in (raw or "").split(",") if m.strip()]

    def model_chain(self, task_type: str = "general") -> list[str]:
        """
        Ordered model fallback chain for a task type.
        Env overrides (comma-separated):
          GEMINI_MODELS            — default chain for all tasks
          GEMINI_MODELS_CHAT       — fast/cheap chain for chat
          GEMINI_MODELS_SCRIPT     — stronger chain for lessons/scripts/reports
        Falls back to the configured GEMINI_MODEL first, then sane defaults.
        """
        settings = get_settings()

        task_attr = {
            "chat": "gemini_models_chat",
            "script": "gemini_models_script",
            "lesson": "gemini_models_script",
            "video": "gemini_models_script",
            "report": "gemini_models_script",
        }.get(task_type, "gemini_models")

        raw_chain = getattr(settings, task_attr, "") or getattr(settings, "gemini_models", "") or ""
        if not isinstance(raw_chain, str):
            raw_chain = ""
        chain = self._parse_chain(raw_chain)
        if not chain:
            chain = self._parse_chain(settings.gemini_models if isinstance(settings.gemini_models, str) else "")
        # Always lead with the explicitly configured primary model
        primary = settings.gemini_model if isinstance(settings.gemini_model, str) else ""
        primary = primary.strip()
        if primary and primary not in chain:
            chain.insert(0, primary)
        # Sane defaults — current stable Gemini IDs; dedup, keep order
        for m in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-flash-latest"):
            if m not in chain:
                chain.append(m)
        # de-dup preserving order
        seen, out = set(), []
        for m in chain:
            if m not in seen:
                seen.add(m)
                out.append(m)
        return out

    # -- pair iteration ---------------------------------------------------

    def _cooldown_for(self, state: _PairState) -> float:
        if state.cooldown_until <= time.time():
            return 0.0
        return state.cooldown_until - time.time()

    def iter_pairs(self, models: list[str]):
        """
        Yield (key_index, key, model) in rotation order, skipping pairs
        currently in cooldown. Keys rotate round-robin within each model.
        """
        keys = self.get_keys()
        if not keys:
            return
        with self._lock:
            start = self._key_index % len(keys)
            now = time.time()
            out = []
            for model in models:
                for offset in range(len(keys)):
                    idx = (start + offset) % len(keys)
                    key = keys[idx]
                    state = self._states.get((idx, model))
                    if state and state.cooldown_until > now:
                        continue
                    out.append((idx, key, model))
        yield from out

    def mark_failure(self, key_index: int, model: str, retry_after: float | None, reason: str):
        with self._lock:
            state = self._states.setdefault((key_index, model), _PairState())
            state.failures += 1
            backoff = min(self.MAX_BACKOFF, self.BASE_BACKOFF * (2 ** (state.failures - 1)))
            backoff *= random.uniform(0.75, 1.25)
            wait = retry_after if retry_after else backoff
            state.cooldown_until = time.time() + max(1.0, wait)
            state.last_error = reason[:200]
            logger.warning(
                "[Gemini] pair key#%d %s / model %s cooled down %.0fs (%s)",
                key_index, self.mask_key(self.get_keys()[key_index]) if key_index < len(self.get_keys()) else "?",
                model, wait, reason[:120],
            )

    def mark_success(self, key_index: int, model: str):
        with self._lock:
            state = self._states.get((key_index, model))
            if state:
                state.failures = 0
                state.cooldown_until = 0.0
                state.last_error = ""
            # advance round-robin so the next request starts on the next key
            keys = self.get_keys()
            if keys:
                self._key_index = (key_index + 1) % len(keys)

    def reset(self):
        """Clear all cooldown/failure state (tests + admin use)."""
        with self._lock:
            self._states.clear()
            self._key_index = 0

    def status(self) -> dict:
        """Diagnostic snapshot for the health endpoint (no key material)."""
        keys = self.get_keys()
        now = time.time()
        with self._lock:
            pairs = []
            for idx, key in enumerate(keys):
                for model in self.model_chain("general"):
                    st = self._states.get((idx, model))
                    pairs.append({
                        "key_index": idx,
                        "key_masked": self.mask_key(key),
                        "model": model,
                        "cooling_down": bool(st and st.cooldown_until > now),
                        "cooldown_remaining_s": round(max(0.0, (st.cooldown_until - now) if st else 0.0), 1),
                        "consecutive_failures": st.failures if st else 0,
                        "last_error": st.last_error if st else "",
                    })
        return {"total_keys": len(keys), "pairs": pairs}


rotator = GeminiRotator()


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def _is_safety_block(detail: str) -> bool:
    d = detail.lower()
    return any(p in d for p in ("safety", "blocked due to", "prohibited_content", "content_policy"))


def _classify_http_error(code: int, detail: str) -> tuple[str, bool]:
    """Return (GeminiError code, rotatable?)."""
    d = detail.lower()
    if code == 429 or "resource_exhausted" in d or "quota" in d or "rate limit" in d or "too many requests" in d:
        return GeminiError.QUOTA_EXHAUSTED, True
    if code == 503 or "overloaded" in d or "unavailable" in d or "capacity" in d:
        return GeminiError.MODEL_UNAVAILABLE, True
    if code in (404, 410):
        return GeminiError.MODEL_UNAVAILABLE, True
    if code in (401, 403) or "api_key_invalid" in d or "api key not valid" in d or \
       "permission_denied" in d or "permissiondenied" in d or "billing" in d or \
       "project has been suspended" in d or "unregistered callers" in d:
        return GeminiError.AUTH_ERROR, True
    if _is_safety_block(detail):
        return GeminiError.SAFETY_BLOCKED, False
    if code == 400:
        return GeminiError.INVALID_REQUEST, False
    return GeminiError.UNKNOWN, False


def _is_rotatable_error(code: int, detail: str) -> bool:
    """Backward-compatible helper: is this HTTP error worth rotating keys/models for?"""
    _, rotatable = _classify_http_error(code, detail or "")
    return rotatable


def _is_rate_limit_error(code: int, detail: str) -> bool:
    return _is_rotatable_error(code, detail)


def _retry_after_seconds(headers) -> float | None:
    try:
        ra = headers.get("Retry-After") if headers else None
        if ra:
            return float(ra)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def _extract_text(payload: dict) -> str:
    cand = payload.get("candidates") or []
    if not cand:
        raise GeminiError(GeminiError.INVALID_RESPONSE, "Gemini returned no candidates")
    # surface explicit blocks
    block_reason = cand[0].get("finishReason") or ""
    parts = cand[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        if "SAFETY" in block_reason.upper() or "BLOCK" in block_reason.upper():
            raise GeminiError(GeminiError.SAFETY_BLOCKED, "Response blocked by safety filters")
        raise GeminiError(GeminiError.INVALID_RESPONSE, "Gemini returned an empty response")
    return text


def generate_content(prompt: str, task_type: str = "general", model: str | None = None,
                     temperature: float | None = None, max_output_tokens: int | None = None,
                     timeout: float = 30.0) -> str:
    """
    Generate text via the multi-provider LLM router (app.services.llm).

    All providers (Gemini + OpenAI-compatible: Groq, OpenRouter, NVIDIA NIM,
    DeepInfra, Cerebras) are tried in the task's chain order with per-pair
    cooldown, quota groups, and dead-model disabling. Raises GeminiError
    with a typed code when every combination is exhausted.
    """
    from app.services.llm import chat as _llm_chat
    return _llm_chat(prompt, task_type=task_type, model=model,
                     temperature=temperature, max_output_tokens=max_output_tokens,
                     timeout=max(timeout, 60.0))


def _generate_content_gemini_only(prompt: str, task_type: str = "general", model: str | None = None,
                                  temperature: float | None = None, max_output_tokens: int | None = None,
                                  timeout: float = 30.0) -> str:
    """Gemini-only generation (legacy path, kept for tests/diagnostics)."""
    settings = get_settings()
    keys = settings.gemini_api_keys
    if not keys:
        raise GeminiError(GeminiError.AUTH_ERROR,
                          "Gemini API key is not configured. Set GEMINI_API_KEY in backend/.env")

    models = [model] if model else rotator.model_chain(task_type)
    last_error: GeminiError | None = None
    attempts = 0
    max_attempts = len(keys) * len(models)

    while attempts < max_attempts:
        progressed = False
        for key_index, key, mdl in rotator.iter_pairs(models):
            attempts += 1
            progressed = True
            masked = rotator.mask_key(key)
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{mdl}:generateContent?key={key}")
            gen_cfg = {}
            if temperature is not None:
                gen_cfg["temperature"] = temperature
            if max_output_tokens is not None:
                gen_cfg["maxOutputTokens"] = max_output_tokens
            body_dict = {"contents": [{"parts": [{"text": prompt}]}]}
            if gen_cfg:
                body_dict["generationConfig"] = gen_cfg
            body = json.dumps(body_dict).encode()
            request = urllib.request.Request(url, data=body,
                                             headers={"Content-Type": "application/json"})
            t0 = time.time()
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode())
                text = _extract_text(payload)
                rotator.mark_success(key_index, mdl)
                logger.info("[Gemini] OK key#%d %s model=%s %.2fs", key_index, masked, mdl, time.time() - t0)
                return text
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode()
                except Exception:
                    pass
                code, rotatable = _classify_http_error(exc.code, detail)
                retry_after = _retry_after_seconds(getattr(exc, "headers", None))
                err = GeminiError(code, f"Gemini API error ({exc.code}): {detail[:200]}")
                last_error = err
                if rotatable:
                    rotator.mark_failure(key_index, mdl, retry_after, f"HTTP {exc.code}: {detail[:120]}")
                    continue
                # non-rotatable: surface immediately
                logger.warning("[Gemini] non-rotatable %s on %s/%s", code, masked, mdl)
                raise err
            except TimeoutError:
                rotator.mark_failure(key_index, mdl, None, "timeout")
                last_error = GeminiError(GeminiError.TIMEOUT, "Gemini request timed out")
                continue
            except urllib.error.URLError as exc:
                # network-level failure — treat as transient, rotate
                rotator.mark_failure(key_index, mdl, None, f"urlerror: {exc}")
                last_error = GeminiError(GeminiError.MODEL_UNAVAILABLE, f"Gemini connection failed: {exc}")
                continue
            except GeminiError as exc:
                # INVALID_RESPONSE / SAFETY_BLOCKED from _extract_text
                if exc.code == GeminiError.SAFETY_BLOCKED:
                    raise
                rotator.mark_failure(key_index, mdl, None, exc.code)
                last_error = exc
                continue
            except Exception as exc:
                rotator.mark_failure(key_index, mdl, None, str(exc)[:120])
                last_error = GeminiError(GeminiError.UNKNOWN, f"Gemini request failed: {exc}")
                continue
        if not progressed:
            break  # every pair is cooling down

    if last_error:
        raise GeminiError(last_error.code,
                          f"All Gemini key/model combinations exhausted. {last_error}")
    raise GeminiError(GeminiError.QUOTA_EXHAUSTED, "No usable Gemini key/model combination available")


def generate_json(prompt: str, task_type: str = "general", **kwargs) -> dict | list:
    parsed = _extract_json(generate_content(prompt, task_type=task_type, **kwargs))
    if parsed is None:
        raise GeminiError(GeminiError.INVALID_RESPONSE, "Gemini response was not valid JSON")
    return parsed


# ---------------------------------------------------------------------------
# Ollama fallback + task router (kept for offline mode)
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | list | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def generate_via_ollama(prompt: str, model_name: str | None = None) -> str:
    """Send a prompt to the local Ollama server and return the text response."""
    settings = get_settings()
    target_model = model_name or settings.ollama_model
    body = json.dumps({
        "model": target_model,
        "prompt": prompt,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        settings.ollama_url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.loads(response.read().decode()).get("response", "")
    except Exception as exc:
        if target_model != settings.ollama_model:
            logger.info("[Ollama] model '%s' failed (%s); retrying '%s'", target_model, exc, settings.ollama_model)
            return generate_via_ollama(prompt, model_name=settings.ollama_model)
        raise


def generate_json_via_ollama(prompt: str, model_name: str | None = None) -> dict | list:
    text = generate_via_ollama(prompt, model_name=model_name)
    parsed = _extract_json(text)
    if parsed is None:
        raise GeminiError(GeminiError.INVALID_RESPONSE,
                          f"Ollama ({model_name or 'default'}) response was not valid JSON")
    return parsed


def translate_text_via_qwen(text: str, target_language: str = "English") -> str:
    """Uses Qwen 2.5 (qwen2.5) to translate or normalize non-English input text."""
    settings = get_settings()
    prompt = f"Translate the following text accurately into {target_language}. Return ONLY the translation:\n\n{text}"
    try:
        return generate_via_ollama(prompt, model_name=settings.ollama_model_translation).strip()
    except Exception:
        return text


def generate_json_any(prompt: str, task_type: str = "general") -> dict | list:
    """
    Gemini-first with Ollama fallback. Task types map to model chains and
    Ollama models:
      - 'translation' -> qwen2.5
      - 'lesson'/'script'/'video'/'report' -> stronger chain
      - 'quiz'        -> llama3.1
      - 'flashcard'   -> llama3.2
      - 'chat'        -> fast chain
    """
    settings = get_settings()

    model_map = {
        "translation": settings.ollama_model_translation,
        "lesson": settings.ollama_model_lesson,
        "script": settings.ollama_model_lesson,
        "video": settings.ollama_model_lesson,
        "report": settings.ollama_model_lesson,
        "quiz": settings.ollama_model_quiz,
        "flashcard": settings.ollama_model_flashcard,
        "chat": settings.ollama_model_flashcard,
    }
    target_ollama_model = model_map.get(task_type, settings.ollama_model)

    # Step 1: Gemini (online) — central client handles key×model rotation
    if settings.gemini_api_keys and settings.ai_provider in ("auto", "gemini"):
        try:
            return generate_json(prompt, task_type=task_type)
        except GeminiError as exc:
            # Don't bother with Ollama for non-transient errors
            if exc.code in (GeminiError.SAFETY_BLOCKED, GeminiError.INVALID_REQUEST):
                raise
            logger.info("[AI Fallback] Gemini unavailable (%s). Switching to Ollama '%s'...",
                        exc.code, target_ollama_model)
        except Exception as exc:
            logger.info("[AI Fallback] Gemini error (%s). Switching to Ollama '%s'...", exc, target_ollama_model)

    # Step 2: Ollama (offline)
    if settings.ai_provider in ("auto", "gemini", "ollama"):
        try:
            return generate_json_via_ollama(prompt, model_name=target_ollama_model)
        except Exception as exc:
            logger.info("[AI Fallback] Ollama '%s' unavailable (%s).", target_ollama_model, exc)

    raise GeminiError(GeminiError.QUOTA_EXHAUSTED,
                      "No working AI provider available (Gemini exhausted and Ollama unreachable)")
