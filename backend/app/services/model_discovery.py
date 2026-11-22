"""Live model discovery and per-key one-token probing (addendum #12 §1).

Every provider is asked for its **live** model list, the candidates are filtered
to text-generation chat models, and each one is probed with a real 1-token chat
completion using that key. Only models that answer are returned to the router, so
routing never guesses a hardcoded name again.

Results are cached in ``backend/data/llm_models.json`` with the probe time so a
restart does not spend quota re-probing.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.services.llm import PROVIDERS, router

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "llm_models.json"
REFRESH_AFTER_SECONDS = 6 * 3600

# Non-chat model families that show up in /models listings.
_NON_CHAT = re.compile(
    r"(whisper|tts|embed|embedding|moderation|guard|rerank|vision-only|"
    r"audio|speech|image|stable-diffusion|flux|clip|ocr|veo|imagen|aqa)",
    re.IGNORECASE,
)


def _http_json(url: str, key: str | None, timeout: float = 15.0) -> Any:
    headers = {"User-Agent": "EduSense-Discovery/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rank(model_id: str) -> tuple[int, str]:
    """Smaller/faster first; newest suffixes and lite/flash variants preferred."""
    low = model_id.lower()
    size = re.search(r"(\d+(?:\.\d+)?)\s*b\b", low)
    params = float(size.group(1)) if size else 70.0
    bonus = 0
    if any(tag in low for tag in ("instant", "lite", "flash", "mini", "small", "8b", "3b", "1b")):
        bonus -= 20
    if any(tag in low for tag in ("pro", "72b", "70b", "405b", "r1")):
        bonus += 20
    return (int(params + bonus), low)


def _list_openai_compatible(provider: str, key: str) -> list[str]:
    spec = PROVIDERS[provider]
    data = _http_json(f"{spec.base_url}/models", key)
    ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
    ids = [i for i in ids if not _NON_CHAT.search(i)]
    if provider == "openrouter":
        # Only truly free models: OpenRouter reports pricing in the list where available.
        free = []
        for m in data.get("data", []):
            mid = m.get("id") or ""
            pricing = m.get("pricing") or {}
            prompt_price = str(pricing.get("prompt", ""))
            if mid.endswith(":free") or prompt_price in ("0", "0.0", "0.00", "0"):
                if not _NON_CHAT.search(mid):
                    free.append(mid)
        ids = free or ids
    return sorted(set(ids), key=_rank)


def _list_gemini(key: str) -> list[str]:
    spec = PROVIDERS["gemini"]
    data = _http_json(f"{spec.base_url}/models?key={key}&pageSize=200", None)
    out = []
    for m in data.get("models", []):
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = (m.get("name") or "").removeprefix("models/")
        if name and not _NON_CHAT.search(name):
            out.append(name)
    return sorted(set(out), key=_rank)


def _list_ollama() -> list[str]:
    data = _http_json("http://localhost:11434/api/tags", None, timeout=5)
    return [m.get("name") for m in data.get("models", []) if m.get("name")]


def _probe(provider: str, key: str, model: str, timeout: float = 25.0) -> dict:
    """Real 1-token chat completion. Returns ok/latency/error body."""
    spec = PROVIDERS[provider]
    t0 = time.time()
    try:
        # 16 tokens, not 1: reasoning/thinking models spend a single token on
        # internal reasoning and return an empty string, which looked like a
        # dead model during discovery.
        if spec.kind == "gemini":
            from app.services.llm import _call_gemini_once
            _call_gemini_once(key, model, "Reply with OK", 0.0, 16, timeout)
        else:
            from app.services.llm import _call_openai_compat
            _call_openai_compat(spec, key, model, "Reply with OK", 0.0, 16, timeout)
        return {"ok": True, "latency_ms": round((time.time() - t0) * 1000), "error": None}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return {
            "ok": False,
            "latency_ms": round((time.time() - t0) * 1000),
            "error": f"HTTP {exc.code}: {body}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": round((time.time() - t0) * 1000),
            "error": str(exc)[:200],
        }


FREE_LIMITS = {
    "groq": {
        "url": "https://console.groq.com/docs/rate-limits",
        "note": "Free tier: per-model RPM/RPD/TPM shown in the console; checked 2026-11-22",
    },
    "nvidia": {
        "url": "https://build.nvidia.com/",
        "note": "Trial credits/limits per account; checked 2026-11-22",
    },
    "openrouter": {
        "url": "https://openrouter.ai/docs/api-reference/limits",
        "note": "Free variants: 20 req/min, 50-1000 req/day depending on credits; checked 2026-11-22",
    },
    "gemini": {
        "url": "https://ai.google.dev/gemini-api/docs/rate-limits",
        "note": "Free tier RPD/TPM per model; shared per Google Cloud project; checked 2026-11-22",
    },
    "ollama": {
        "url": "https://github.com/ollama/ollama/blob/main/docs/faq.md",
        "note": "Local, no quota",
    },
}


def discover(models_per_provider: int = 8, include_ollama: bool = True) -> dict[str, Any]:
    """Ask every provider for its live models, probe the top candidates per key."""
    started = time.time()
    report: dict[str, Any] = {
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "providers": {},
        "working": {},
    }

    for provider, spec in PROVIDERS.items():
        if provider == "ollama":
            continue
        keys = router.provider_keys(provider)
        if not keys:
            continue
        provider_rows: list[dict] = []
        working_union: list[str] = []
        for idx, key in enumerate(keys):
            try:
                listed = (
                    _list_gemini(key) if spec.kind == "gemini"
                    else _list_openai_compatible(provider, key)
                )
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    pass
                provider_rows.append({
                    "key_masked": router.mask_key(key),
                    "list_error": f"HTTP {exc.code}: {body}",
                    "models": [],
                })
                continue
            except Exception as exc:
                provider_rows.append({
                    "key_masked": router.mask_key(key),
                    "list_error": str(exc)[:200],
                    "models": [],
                })
                continue

            probed = []
            for model in listed[:models_per_provider]:
                result = _probe(provider, key, model)
                probed.append({"id": model, **result})
                if result["ok"] and model not in working_union:
                    working_union.append(model)
            provider_rows.append({
                "key_masked": router.mask_key(key),
                "list_error": None,
                "models": probed,
            })
        if not provider_rows:
            continue
        report["providers"][provider] = {
            "limits": FREE_LIMITS.get(provider),
            "keys": provider_rows,
            "working_models": working_union,
        }
        report["working"][provider] = working_union

    if include_ollama:
        try:
            tags = _list_ollama()
        except Exception as exc:
            tags = []
            report["providers"]["ollama"] = {
                "limits": FREE_LIMITS["ollama"],
                "running": False,
                "error": str(exc)[:160],
                "keys": [],
                "working_models": [],
            }
        else:
            report["providers"]["ollama"] = {
                "limits": FREE_LIMITS["ollama"],
                "running": True,
                "keys": [{"key_masked": "local", "list_error": None,
                          "models": [{"id": m, "ok": True, "latency_ms": None,
                                      "error": None} for m in tags]}],
                "working_models": tags,
            }
            report["working"]["ollama"] = tags

    report["elapsed_s"] = round(time.time() - started, 1)
    report["cache_path"] = str(CACHE_PATH)

    # Feed the router: only models that answered are offered.
    router.set_working_models(report["working"])

    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report


def load_cache() -> dict[str, Any] | None:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    # Keep routing honest even on a warm start.
    try:
        router.set_working_models(data.get("working") or {})
    except Exception:
        pass
    return data


def cache_age_seconds(report: dict[str, Any] | None) -> float:
    if not report:
        return float("inf")
    return time.time() - float(report.get("generated_at") or 0)
