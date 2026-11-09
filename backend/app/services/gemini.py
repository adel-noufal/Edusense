import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request

from app.core.config import get_settings

logger = logging.getLogger(__name__)


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
    return None


class GeminiKeyRotator:
    """
    Thread-safe multi-API-key rotator for Google Gemini.
    Automatically switches to the next available key upon hitting rate limits (HTTP 429,
    RESOURCE_EXHAUSTED, or quota exceeded), with automatic recovery after cooldown.
    """
    def __init__(self, cooldown_seconds: float = 60.0):
        self._lock = threading.Lock()
        self._current_index = 0
        self._cooldown_seconds = cooldown_seconds
        self._exhausted: dict[str, float] = {}

    def mask_key(self, key: str) -> str:
        if not key or len(key) < 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    def get_keys(self) -> list[str]:
        settings = get_settings()
        return settings.gemini_api_keys

    def get_active_key(self) -> str | None:
        """Returns the currently active key, recovering cooled-down keys."""
        with self._lock:
            keys = self.get_keys()
            if not keys:
                return None

            now = time.time()
            for k in list(self._exhausted.keys()):
                if now - self._exhausted[k] >= self._cooldown_seconds:
                    logger.info(f"[Gemini Key Rotation] Key {self.mask_key(k)} cooldown elapsed, restored.")
                    del self._exhausted[k]

            total = len(keys)
            for i in range(total):
                idx = (self._current_index + i) % total
                candidate = keys[idx]
                if candidate not in self._exhausted:
                    self._current_index = idx
                    return candidate

            # All currently exhausted; return the one that expired earliest
            return min(keys, key=lambda k: self._exhausted.get(k, 0))

    def mark_exhausted(self, key: str, reason: str = "") -> str | None:
        """Marks a key as exhausted and advances to the next available key."""
        with self._lock:
            keys = self.get_keys()
            self._exhausted[key] = time.time()
            masked = self.mask_key(key)
            logger.warning(
                f"[Gemini Key Rotation] Key {masked} rate limited / exhausted ({reason}). Rotating..."
            )
            total = len(keys)
            for i in range(1, total + 1):
                idx = (self._current_index + i) % total
                candidate = keys[idx]
                if candidate not in self._exhausted:
                    self._current_index = idx
                    logger.info(f"[Gemini Key Rotation] Switched to active key {self.mask_key(candidate)} (index {idx}).")
                    return candidate

            logger.error("[Gemini Key Rotation] All configured Gemini API keys are currently exhausted.")
            return None

    def status(self) -> dict:
        with self._lock:
            keys = self.get_keys()
            now = time.time()
            active_count = sum(1 for k in keys if k not in self._exhausted or (now - self._exhausted[k] >= self._cooldown_seconds))
            return {
                "total_keys": len(keys),
                "active_keys": active_count,
                "exhausted_keys": len(keys) - active_count,
                "current_index": self._current_index,
            }

rotator = GeminiKeyRotator()


def _is_rate_limit_error(exc_code: int, detail: str) -> bool:
    if exc_code == 429:
        return True
    lower = detail.lower()
    return any(phrase in lower for phrase in (
        "resource_exhausted",
        "quota exceeded",
        "rate limit",
        "rate_limit",
        "too many requests",
        "per-minute quota",
    ))


def generate_content(prompt: str) -> str:
    settings = get_settings()
    keys = settings.gemini_api_keys
    if not keys:
        raise RuntimeError("Gemini API key is not configured. Set EDUSENSE_GEMINI_API_KEY in backend/.env")

    max_attempts = len(keys)
    last_error = None

    for _ in range(max_attempts):
        key = rotator.get_active_key()
        if not key:
            break

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent?key={key}"
        )
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode())

            candidates = payload.get("candidates") or []
            if not candidates:
                raise RuntimeError("Gemini returned no candidates")
            parts = candidates[0].get("content", {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts).strip()
            if not text:
                raise RuntimeError("Gemini returned an empty response")
            return text

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            if _is_rate_limit_error(exc.code, detail):
                rotator.mark_exhausted(key, reason=f"HTTP {exc.code}")
                last_error = f"HTTP {exc.code}: {detail[:150]}"
                continue
            raise RuntimeError(f"Gemini API error ({exc.code}): {detail[:240]}") from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini connection failed (offline or network error): {exc}") from exc
        except Exception as exc:
            if "Gemini returned" in str(exc):
                raise
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

    raise RuntimeError(
        f"All configured Gemini API keys ({len(keys)} key(s)) are currently exhausted or rate-limited. Last error: {last_error}"
    )


def generate_json(prompt: str) -> dict | list:
    parsed = _extract_json(generate_content(prompt))
    if parsed is None:
        raise RuntimeError("Gemini response was not valid JSON")
    return parsed


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
        # If target model fails (e.g. not pulled locally), fallback to master model
        if target_model != settings.ollama_model:
            print(f"[Ollama Fallback] Model '{target_model}' failed ({exc}). Retrying with master model '{settings.ollama_model}'...")
            return generate_via_ollama(prompt, model_name=settings.ollama_model)
        raise


def generate_json_via_ollama(prompt: str, model_name: str | None = None) -> dict | list:
    """Send a JSON-requesting prompt to Ollama and parse the response."""
    text = generate_via_ollama(prompt, model_name=model_name)
    parsed = _extract_json(text)
    if parsed is None:
        raise RuntimeError(f"Ollama ({model_name or 'default'}) response was not valid JSON")
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
    Intelligent 4-Model AI Router with Automatic Fallback:
    Task Model Mapping (Offline):
      - 'translation' -> Qwen 2.5   (qwen2.5: best multilingual & Arabic translation)
      - 'lesson'      -> Mistral    (mistral: best 7B model for structured lessons & slides)
      - 'quiz'        -> Llama 3.1  (llama3.1: best 8B reasoning for assessment questions)
      - 'flashcard'   -> Llama 3.2  (llama3.2: fast 3B model for quick study decks)
    """
    settings = get_settings()

    model_map = {
        "translation": settings.ollama_model_translation,
        "lesson": settings.ollama_model_lesson,
        "quiz": settings.ollama_model_quiz,
        "flashcard": settings.ollama_model_flashcard,
    }
    target_ollama_model = model_map.get(task_type, settings.ollama_model)

    # Step 1: Attempt Gemini (Online) first if key exists and provider is auto/gemini
    if settings.gemini_api_key and settings.ai_provider in ("auto", "gemini"):
        try:
            return generate_json(prompt)
        except Exception as exc:
            print(f"[AI Fallback] Gemini API unavailable ({exc}). Automatically switching to Ollama model '{target_ollama_model}'...")

    # Step 2: Fallback to specialized local Ollama model if Gemini failed or provider is ollama/auto
    if settings.ai_provider in ("auto", "gemini", "ollama"):
        try:
            return generate_json_via_ollama(prompt, model_name=target_ollama_model)
        except Exception as exc:
            print(f"[AI Fallback] Local Ollama ({target_ollama_model}) unavailable ({exc}). Using template fallback...")

    raise RuntimeError("No working AI provider available (Gemini offline and Ollama unreachable)")




