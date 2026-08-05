import json
import re
import urllib.error
import urllib.request

from app.core.config import get_settings


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


def generate_content(prompt: str) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Gemini API key is not configured. Set EDUSENSE_GEMINI_API_KEY in backend/.env")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        # Reduced timeout (15s) so offline detection & fallback to Ollama happens quickly
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"Gemini API error ({exc.code}): {detail[:240]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini connection failed (offline or network error): {exc}") from exc

    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response")
    return text


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




