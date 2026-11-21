"""
llm.py â€” Open-ended Multi-Provider, Multi-Key LLM Layer for EduSense (Part A Revised).

Key architectural capabilities:
1. Dynamic unlimited key discovery from .env and environment:
     <PROVIDER>_API_KEYS=k1,k2,k3          (pooled comma list)
     <PROVIDER>_KEY_<LABEL>=...            (named key: e.g. GEMINI_KEY_VIDEO_1, GROQ_KEY_CHAT)
     Full backward compatibility with existing GEMINI_API_KEY, GEMINI_API_KEY_N, CHATBOT_GEMINI_API_KEY.
2. Per-key metadata & quota-group tracking:
     - Group cooldown across keys sharing the same Google Cloud project or provider account.
     - Dedicated feature assignment (e.g. video, chat, quiz, report) prioritizing dedicated keys.
3. Startup & on-demand key validation:
     - Probes keys with lightweight ping, classifies healthy / invalid / rate-limited / no-access-to-model.
     - Auto-disables bad keys with masked warnings (revealing only last 4 chars).
4. Best-fit capability-driven routing:
     - Model capability profiles (context, output, speed, Arabic, strict-JSON, streaming, privacy).
     - Feature requirements scoring (video_script, kb_chat, quizzes, reports, question_bank).
     - Dedicated keys prioritized for their feature; protected as last-resort spillover for others.
     - Load-balancing across keys of the same tier (round-robin / least-recently-used).
     - Strict-JSON validation with one repair attempt before rotating.
     - Answer-verification provider divergence (preferring different provider).
5. Visibility and control:
     - Diagnostic CLI script + admin endpoints (/api/admin/llm-status, /api/admin/llm-test).
     - Persistent daily usage counter per key and provider.
     - Detailed per-request operational logs.
"""
import concurrent.futures
import copy
import json
import logging
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.gemini import GeminiError, _classify_http_error, _extract_json, _is_safety_block

logger = logging.getLogger(__name__)

# Base paths
CONFIG_PATH = Path(__file__).resolve().parent.parent / "core" / "llm_config.json"
USAGE_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "llm_usage.json"


# ---------------------------------------------------------------------------
# Provider & Model Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderSpec:
    name: str
    kind: str                      # "gemini" | "openai"
    base_url: str
    auth_style: str = "bearer"     # "bearer" | "query_param"
    default_models: tuple[str, ...] = ()


def _load_config_file() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("[LLM] Failed reading %s: %s", CONFIG_PATH, exc)
    return {}


_RAW_CONFIG = _load_config_file()


def _build_provider_specs() -> dict[str, ProviderSpec]:
    specs = {
        "gemini": ProviderSpec(
            name="gemini", kind="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            auth_style="query_param",
            default_models=("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-flash-latest", "gemini-2.5-pro"),
        ),
        "groq": ProviderSpec(
            name="groq", kind="openai",
            base_url="https://api.groq.com/openai/v1",
            auth_style="bearer",
            default_models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"),
        ),
        "cerebras": ProviderSpec(
            name="cerebras", kind="openai",
            base_url="https://api.cerebras.ai/v1",
            auth_style="bearer",
            default_models=("llama-3.3-70b", "llama3.1-8b"),
        ),
        "openrouter": ProviderSpec(
            name="openrouter", kind="openai",
            base_url="https://openrouter.ai/api/v1",
            auth_style="bearer",
            default_models=("meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-001",
                            "deepseek/deepseek-chat", "openai/gpt-4o-mini", "qwen/qwen-2.5-72b-instruct"),
        ),
        "nvidia": ProviderSpec(
            name="nvidia", kind="openai",
            base_url="https://integrate.api.nvidia.com/v1",
            auth_style="bearer",
            default_models=("meta/llama-3.3-70b-instruct", "deepseek-ai/deepseek-v3.1",
                            "qwen/qwen2.5-72b-instruct", "deepseek-ai/deepseek-r1"),
        ),
        "deepinfra": ProviderSpec(
            name="deepinfra", kind="openai",
            base_url="https://api.deepinfra.com/v1/openai",
            auth_style="bearer",
            default_models=("meta-llama/Meta-Llama-3.1-70B-Instruct",
                            "Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"),
        ),
        "ollama": ProviderSpec(
            name="ollama", kind="openai",
            base_url="http://localhost:11434/v1",
            auth_style="none",
            default_models=("llama3.1:latest", "qwen2.5:latest", "mistral:latest", "llama3.2:latest"),
        ),
    }

    file_providers = _RAW_CONFIG.get("providers", {})
    for pname, pdata in file_providers.items():
        pname_lower = pname.lower().strip()
        specs[pname_lower] = ProviderSpec(
            name=pname_lower,
            kind=pdata.get("kind", "openai"),
            base_url=pdata.get("base_url", ""),
            auth_style=pdata.get("auth_style", "bearer"),
            default_models=tuple(pdata.get("default_models", [])),
        )
    return specs


PROVIDERS: dict[str, ProviderSpec] = _build_provider_specs()

# Task aliases
_TASK_ALIASES = {
    "video": "video_script",
    "script": "video_script",
    "prompt_enhance": "prompt_enhance",
    "chat": "kb_chat",
    "chatbot": "kb_chat",
    "quiz": "quizzes",
    "exam": "exams",
    "flashcard": "flashcards",
    "report": "reports",
    "recommendation": "recommendations",
    "translation": "general",
    "lesson": "video_script",
}

# Default feature provider starting preference chains
DEFAULT_FEATURE_CHAINS: dict[str, tuple[str, ...]] = {
    "prompt_enhance":  ("ollama", "groq", "cerebras", "gemini", "openrouter", "nvidia", "deepinfra"),
    "video_script":    ("gemini", "openrouter", "nvidia", "groq", "deepinfra", "cerebras", "ollama"),
    "kb_chat":         ("groq", "gemini", "openrouter", "nvidia", "deepinfra", "cerebras", "ollama"),
    "quizzes":         ("nvidia", "openrouter", "deepinfra", "groq", "gemini", "cerebras", "ollama"),
    "flashcards":      ("nvidia", "openrouter", "deepinfra", "groq", "gemini", "cerebras", "ollama"),
    "exams":           ("nvidia", "openrouter", "deepinfra", "groq", "gemini", "cerebras", "ollama"),
    "reports":         ("gemini", "groq", "nvidia", "openrouter", "deepinfra", "cerebras", "ollama"),
    "recommendations": ("gemini", "groq", "nvidia", "openrouter", "deepinfra", "cerebras", "ollama"),
    "question_bank":   ("groq", "cerebras", "gemini", "nvidia", "openrouter", "deepinfra", "ollama"),
    "general":         ("gemini", "groq", "openrouter", "nvidia", "deepinfra", "cerebras", "ollama"),
}


# ---------------------------------------------------------------------------
# Key Entry & Metadata Model
# ---------------------------------------------------------------------------

@dataclass
class KeyEntry:
    provider: str
    key: str
    label: str = "default"
    quota_group: str = ""
    dedicated_features: set[str] = field(default_factory=set)
    priority: int = 100
    status: str = "healthy"         # "healthy" | "rate_limited" | "invalid" | "no_access" | "disabled" | "untested"
    disabled: bool = False
    failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    requests_today: int = 0
    tokens_today: int = 0
    last_used: float = 0.0
    env_var: str = ""

    @property
    def masked(self) -> str:
        k = self.key.strip()
        if not k or len(k) < 8:
            return "***"
        return f"{k[:4]}...{k[-4:]}"

    @property
    def masked_last4(self) -> str:
        k = self.key.strip()
        if not k or len(k) < 4:
            return "***"
        return f"...{k[-4:]}"

    def is_dedicated_for(self, feature: str) -> bool:
        norm = _TASK_ALIASES.get(feature, feature)
        return norm in self.dedicated_features or feature in self.dedicated_features

    def has_other_dedication(self, feature: str) -> bool:
        if not self.dedicated_features:
            return False
        norm = _TASK_ALIASES.get(feature, feature)
        return not (norm in self.dedicated_features or feature in self.dedicated_features)


# ---------------------------------------------------------------------------
# Per-Pair Candidate State (for direct backward-compatible access)
# ---------------------------------------------------------------------------

@dataclass
class _CandState:
    failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    disabled: bool = False          # permanent (404 model gone)
    requests: int = 0
    last_used: float = 0.0


# ---------------------------------------------------------------------------
# Usage Counter (Persistent Daily Free Quota Tracking)
# ---------------------------------------------------------------------------

class UsageTracker:
    def __init__(self, filepath: Path):
        self._path = filepath
        self._lock = threading.Lock()
        self._today = time.strftime("%Y-%m-%d")
        self._data: dict[str, Any] = {"date": self._today, "keys": {}, "providers": {}}
        self._load()

    def _load(self):
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if content.get("date") == self._today:
                        self._data = content
        except Exception:
            pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def record(self, provider: str, masked_key: str, est_tokens: int = 0):
        with self._lock:
            cur_day = time.strftime("%Y-%m-%d")
            if cur_day != self._today:
                self._today = cur_day
                self._data = {"date": cur_day, "keys": {}, "providers": {}}

            k_stats = self._data["keys"].setdefault(f"{provider}:{masked_key}", {"requests": 0, "tokens": 0})
            k_stats["requests"] += 1
            k_stats["tokens"] += est_tokens

            p_stats = self._data["providers"].setdefault(provider, {"requests": 0, "tokens": 0})
            p_stats["requests"] += 1
            p_stats["tokens"] += est_tokens
            self._save()

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)


_usage_tracker = UsageTracker(USAGE_FILE_PATH)


# ---------------------------------------------------------------------------
# LLM Router & Registry
# ---------------------------------------------------------------------------

class LLMRouter:
    BASE_BACKOFF = 30.0
    MAX_BACKOFF = 900.0

    def __init__(self):
        self._lock = threading.RLock()
        self._keys: list[KeyEntry] = []
        self._keys_by_provider: dict[str, list[KeyEntry]] = {}
        self._group_cd: dict[tuple[str, str, str], float] = {}   # (provider, group, model) -> until
        self._states: dict[tuple[str, int, str], _CandState] = {}
        self._model_disabled: dict[tuple[str, str], bool] = {}   # (provider, model) -> bool
        self._discovered: dict[str, list[str] | None] = {}
        self._discovered_at: dict[str, float] = {}
        self._rr: dict[str, int] = {}
        self.reload_keys()

    # -- Key Discovery & Registry ------------------------------------------

    def reload_keys(self):
        """
        Auto-discover all keys from environment and .env without hardcoded key counts.
        Conventions:
          1. <PROVIDER>_KEY_<LABEL>=...         (named key: e.g. GEMINI_KEY_VIDEO_1)
          2. <PROVIDER>_API_KEYS=k1,k2,k3       (pooled comma list)
          3. Backward compatibility:
             GEMINI_API_KEY, EDUSENSE_GEMINI_API_KEY, GEMINI_API_KEY_1..., CHATBOT_GEMINI_API_KEY
             EDUSENSE_<PROVIDER>_API_KEYS
        """
        with self._lock:
            self._keys.clear()
            self._keys_by_provider.clear()

            try:
                get_settings.cache_clear()
            except Exception:
                pass

            env_map = dict(os.environ)
            backend_env = Path("backend/.env")
            if not backend_env.exists():
                backend_env = Path(".env")
            if backend_env.exists():
                try:
                    for line in backend_env.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k and v and k not in env_map:
                            env_map[k] = v
                except Exception:
                    pass

            discovered: list[KeyEntry] = []
            seen_keys_by_prov: dict[str, set[str]] = {}

            def add_key(pname: str, kstr: str, label: str, env_var: str = "", group: str = "", features: set[str] | None = None, prio: int = 100):
                kstr = kstr.strip().strip("'").strip('"')
                if not kstr:
                    return
                pname = pname.lower().strip()
                if pname not in seen_keys_by_prov:
                    seen_keys_by_prov[pname] = set()
                if kstr in seen_keys_by_prov[pname]:
                    return
                seen_keys_by_prov[pname].add(kstr)

                feat_set = set(features) if features else set()
                lbl_lower = label.lower()
                if not feat_set:
                    if "video" in lbl_lower:
                        feat_set.add("video_script")
                    if "chat" in lbl_lower or "chatbot" in lbl_lower:
                        feat_set.add("kb_chat")
                        feat_set.add("chatbot")
                    if "quiz" in lbl_lower or "exam" in lbl_lower:
                        feat_set.add("quizzes")
                        feat_set.add("exams")
                    if "report" in lbl_lower:
                        feat_set.add("reports")
                    if "bulk" in lbl_lower or "bank" in lbl_lower:
                        feat_set.add("question_bank")

                qgroup = group.strip()
                if not qgroup:
                    g_var = f"{pname.upper()}_KEY_{label.upper()}_GROUP"
                    eg_var = f"EDUSENSE_{pname.upper()}_KEY_{label.upper()}_GROUP"
                    qgroup = env_map.get(g_var) or env_map.get(eg_var) or ""
                if not qgroup:
                    qgroup = f"{pname}:{label}"

                entry = KeyEntry(
                    provider=pname,
                    key=kstr,
                    label=label,
                    quota_group=qgroup,
                    dedicated_features=feat_set,
                    priority=prio,
                    env_var=env_var,
                )
                discovered.append(entry)

            # 1. Named keys first (<PROVIDER>_KEY_<LABEL>) to preserve specific labels & dedicated tags
            for env_name, env_val in sorted(env_map.items()):
                val = env_val.strip()
                if not val:
                    continue
                norm_name = env_name.upper()
                if norm_name.startswith("EDUSENSE_"):
                    norm_name = norm_name[len("EDUSENSE_"):]

                if "_KEY_" in norm_name and not norm_name.endswith(("_GROUP", "_FEATURE", "_PRIORITY")):
                    parts = norm_name.split("_KEY_", 1)
                    pname = parts[0].lower()
                    label = parts[1].lower()
                    f_var = f"{env_name}_FEATURE"
                    feat_override = env_map.get(f_var, "").strip()
                    f_set = {feat_override} if feat_override else None
                    add_key(pname, val, label, env_var=env_name, features=f_set)

            # 2. Dedicated chatbot key
            cb_key = env_map.get("CHATBOT_GEMINI_API_KEY") or env_map.get("EDUSENSE_CHATBOT_GEMINI_API_KEY") or ""
            if cb_key.strip():
                add_key("gemini", cb_key.strip(), "chatbot", env_var="CHATBOT_GEMINI_API_KEY",
                        features={"kb_chat", "chatbot"})

            # 3. Pooled keys: <PROVIDER>_API_KEYS=k1,k2,k3
            for env_name, env_val in sorted(env_map.items()):
                val = env_val.strip()
                if not val:
                    continue
                norm_name = env_name.upper()
                if norm_name.startswith("EDUSENSE_"):
                    norm_name = norm_name[len("EDUSENSE_"):]

                if norm_name.endswith("_API_KEYS"):
                    pname = norm_name[:-len("_API_KEYS")].lower()
                    for i, kpart in enumerate(val.split(",")):
                        kpart = kpart.strip()
                        if kpart:
                            add_key(pname, kpart, f"pool_{i+1}", env_var=env_name)

                elif "_API_KEY_" in norm_name and not norm_name.endswith(("_GROUP", "_FEATURE", "_PRIORITY")):
                    parts = norm_name.split("_API_KEY_", 1)
                    pname = parts[0].lower()
                    label = f"key_{parts[1].lower()}"
                    add_key(pname, val, label, env_var=env_name)

            # 4. Legacy GEMINI_API_KEY / EDUSENSE_GEMINI_API_KEY
            for k_var in ("GEMINI_API_KEY", "EDUSENSE_GEMINI_API_KEY"):
                raw_gem = env_map.get(k_var, "").strip()
                if raw_gem:
                    for i, k in enumerate(raw_gem.split(",")):
                        k = k.strip()
                        if k:
                            add_key("gemini", k, f"gemini_{i+1}", env_var=k_var)

            # 5. Fallback from Settings to catch anything dynamically configured
            s = get_settings()
            for idx, k in enumerate(s.gemini_api_keys):
                add_key("gemini", k, f"gemini_{idx+1}", env_var="Settings.gemini_api_keys")

            # 6. Ollama â€” no API key needed; use a dummy sentinel so provider_keys returns non-empty.
            #    Check if Ollama is reachable before adding.
            raw_ollama = env_map.get("EDUSENSE_OLLAMA_URL", "http://localhost:11434")
            ollama_base = raw_ollama.split("/api")[0].rstrip("/")
            try:
                import urllib.request as _ur
                _ur.urlopen(f"{ollama_base}/api/tags", timeout=2).read()
                add_key("ollama", "ollama-local", "local", env_var="OLLAMA_SENTINEL")
                logger.info("[LLM] Ollama reachable at %s â€” 4 local models registered", ollama_base)
            except Exception as _exc:
                logger.info("[LLM] Ollama not reachable at %s: %s", ollama_base, _exc)

            self._keys = discovered
            for e in self._keys:
                self._keys_by_provider.setdefault(e.provider, []).append(e)

            logger.info("[LLM] Discovered %d keys across %d providers: %s",
                        len(self._keys), len(self._keys_by_provider),
                        {p: len(ks) for p, ks in self._keys_by_provider.items()})

    @staticmethod
    def mask_key(key: str) -> str:
        if not key or len(key) < 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    @staticmethod
    def mask_last4(key: str) -> str:
        if not key or len(key) < 4:
            return "***"
        return f"...{key[-4:]}"

    def provider_keys(self, provider: str) -> list[str]:
        """Return raw active key strings for a provider."""
        provider = provider.lower()
        if provider == "gemini":
            from app.services.gemini import rotator as _grot
            return _grot.get_keys()
        with self._lock:
            entries = self._keys_by_provider.get(provider, [])
            if entries:
                return [e.key for e in entries if not e.disabled]
        s = get_settings()
        raw = getattr(s, f"{provider}_api_keys", "") or ""
        if isinstance(raw, str):
            return [k.strip() for k in raw.split(",") if k.strip()]
        return []

    def key_group(self, provider: str, key_index: int) -> str:
        """Quota group for a key."""
        s = get_settings()
        if provider == "gemini":
            raw = getattr(s, "gemini_key_groups", "") or ""
            for part in raw.split(","):
                part = part.strip()
                if not part or ":" not in part:
                    continue
                k, g = part.split(":", 1)
                if k.strip().isdigit() and int(k.strip()) == key_index:
                    return g.strip() or str(key_index)
        with self._lock:
            entries = self._keys_by_provider.get(provider, [])
            if key_index < len(entries):
                return entries[key_index].quota_group or str(key_index)
        return str(key_index)

    def provider_models(self, provider: str, task_type: str = "general") -> list[str]:
        """Configured model chain for a provider."""
        s = get_settings()
        spec = PROVIDERS.get(provider)
        if not spec:
            return []
        if provider == "gemini":
            from app.services.gemini import rotator
            return rotator.model_chain(task_type)

        raw = getattr(s, f"{provider}_models", "") or ""
        models = [m.strip() for m in raw.split(",") if m.strip()] if isinstance(raw, str) else []
        if not models:
            models = list(spec.default_models)
        seen, out = set(), []
        for m in models:
            if m not in seen:
                seen.add(m); out.append(m)
        return out

    # -- Model Capability Profile & Requirements Matching ------------------

    def get_model_profile(self, provider: str, model: str) -> dict:
        """Fetch verified model capability profile from config or sane fallback."""
        profiles = _RAW_CONFIG.get("model_profiles", {}).get(provider, {})
        if model in profiles:
            return profiles[model]
        for k, v in profiles.items():
            if model.endswith(k) or k.endswith(model):
                return v
        return {
            "context_window": 32768,
            "max_output_tokens": 4096,
            "speed": "high",
            "arabic_quality": "medium",
            "json_reliability": "medium",
            "streaming": True,
            "cost": "free",
            "may_train_on_data": False,
        }

    def get_feature_requirements(self, task_type: str) -> dict:
        """Fetch feature requirements from config."""
        task = _TASK_ALIASES.get(task_type, task_type)
        reqs = _RAW_CONFIG.get("feature_requirements", {})
        return reqs.get(task) or reqs.get("general") or {
            "min_context": 4000,
            "min_output": 1000,
            "strict_json": False,
            "provider_affinity": ["gemini", "groq", "openrouter", "nvidia", "deepinfra", "cerebras"],
        }

    # -- Best-Fit Candidate Scoring & Ordering -----------------------------

    def _chain_override(self, task_type: str) -> list[tuple[str, str]] | None:
        """EDUSENSE_LLM_CHAIN_<TASK>=provider:model,provider:model explicit chain."""
        env_name = f"EDUSENSE_LLM_CHAIN_{task_type.upper()}"
        raw = os.environ.get(env_name, "")
        if not raw:
            return None
        out = []
        for part in raw.split(","):
            part = part.strip()
            if ":" in part:
                p, m = part.split(":", 1)
                out.append((p.strip(), m.strip()))
        return out or None

    def candidates(self, task_type: str = "general", prompt_tokens: int = 100,
                   exclude_provider: str | None = None, touch_student_data: bool = False
                   ) -> list[tuple[str, int, str, str]]:
        """
        Build ordered best-fit candidates: (provider, key_index, key, model).
        """
        task = _TASK_ALIASES.get(task_type, task_type)
        override = self._chain_override(task) or self._chain_override("general")

        triples: list[tuple[str, str]] = []  # (provider, model)
        if override:
            triples = [(p, m) for p, m in override if p in PROVIDERS and (not exclude_provider or p.lower() != exclude_provider.lower())]
        else:
            req = self.get_feature_requirements(task)
            prov_order = DEFAULT_FEATURE_CHAINS.get(task) or DEFAULT_FEATURE_CHAINS["general"]
            for pname in prov_order:
                if exclude_provider and pname.lower() == exclude_provider.lower():
                    continue
                keys = self.provider_keys(pname)
                if not keys:
                    continue

                models = self._discovered.get(pname)
                if models is None:
                    models = self.provider_models(pname, task)

                for m in models:
                    if self._model_disabled.get((pname, m)):
                        continue
                    profile = self.get_model_profile(pname, m)
                    ctx = profile.get("context_window", 32768)
                    if ctx < (prompt_tokens + req.get("min_output", 500)):
                        continue
                    out_cap = profile.get("max_output_tokens", 4096)
                    if out_cap < min(req.get("min_output", 500), 1000):
                        continue
                    if touch_student_data and profile.get("may_train_on_data", False):
                        continue
                    if not getattr(get_settings(), "allow_paid_models", False):
                        is_free = profile.get("free_tier", profile.get("cost") == "free")
                        if pname == "openrouter" and not m.endswith(":free"):
                            is_free = False
                        if pname == "deepinfra":
                            is_free = False
                        if not is_free:
                            continue
                    triples.append((pname, m))

        out: list[tuple[str, int, str, str]] = []
        with self._lock:
            for pname, model in triples:
                keys = self.provider_keys(pname)
                if not keys:
                    continue

                entry_map = {e.key: e for e in self._keys_by_provider.get(pname, [])}
                start = self._rr.get(pname, 0) % len(keys)
                rr_indices = [(start + off) % len(keys) for off in range(len(keys))]

                def key_sort_score(idx: int) -> float:
                    kstr = keys[idx]
                    ke = entry_map.get(kstr)
                    if ke and ke.is_dedicated_for(task):
                        return 1000.0
                    if ke and ke.has_other_dedication(task):
                        return -500.0
                    return 0.0

                sorted_indices = sorted(rr_indices, key=key_sort_score, reverse=True)

                for idx in sorted_indices:
                    kstr = keys[idx]
                    out.append((pname, idx, kstr, model))
        return out

    # -- Model Discovery ---------------------------------------------------

    def discover_models(self, provider: str, force: bool = False, task_type: str = "general") -> list[str] | None:
        """Query /models on provider and intersect with configured chain."""
        spec = PROVIDERS.get(provider)
        if not spec:
            return None
        now = time.time()
        if not force and provider in self._discovered and now - self._discovered_at.get(provider, 0) < 600:
            return self._discovered[provider]

        configured = self.provider_models(provider, task_type)
        keys = self.provider_keys(provider)
        if not keys:
            return configured

        available: set[str] | None = None
        try:
            if spec.kind == "openai":
                url = f"{spec.base_url}/models"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {keys[0]}"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode())
                ids = {m.get("id") for m in data.get("data", []) if m.get("id")}
                available = {m for m in configured if m in ids or any(m.endswith("/" + i) or i.endswith("/" + m) for i in ids)}
            else:
                url = f"{spec.base_url}/models?key={keys[0]}&pageSize=200"
                with urllib.request.urlopen(url, timeout=12) as resp:
                    data = json.loads(resp.read().decode())
                ids = {m.get("name", "").removeprefix("models/") for m in data.get("models", [])}
                gen_ids = {i for i, m in zip(ids, data.get("models", []))
                           if "generateContent" in (m.get("supportedGenerationMethods") or [])}
                pool = gen_ids or ids
                available = {m for m in configured if m in pool}
        except Exception as exc:
            logger.info("[LLM] model discovery failed for %s: %s", provider, exc)
            self._discovered[provider] = None
            self._discovered_at[provider] = now
            return None

        filtered = [m for m in configured if m in available] if available else configured
        self._discovered[provider] = filtered
        self._discovered_at[provider] = now
        return filtered

    # -- Cooldown and Health State -----------------------------------------

    def _state(self, provider: str, key_index: int, model: str) -> _CandState:
        return self._states.setdefault((provider, key_index, model), _CandState())

    def _group_blocked(self, provider: str, group: str, model: str) -> float:
        until = self._group_cd.get((provider, group, model), 0.0)
        return max(0.0, until - time.time())

    def mark_failure(self, provider: str, key_index: int, model: str, retry_after: float | None,
                     reason: str, permanent: bool = False, quota_group: str | None = None):
        with self._lock:
            st = self._state(provider, key_index, model)
            st.failures += 1
            st.last_error = reason[:200]
            st.last_used = time.time()

            entries = self._keys_by_provider.get(provider, [])
            kentry = entries[key_index] if key_index < len(entries) else None
            if kentry:
                kentry.failures += 1
                kentry.last_error = reason[:200]
                kentry.last_used = time.time()

            if permanent or "no longer available" in reason.lower() or ("not found" in reason.lower() and "model" in reason.lower()):
                st.disabled = True
                # Only disable model globally across provider if all keys have failed for it
                all_disabled = True
                for kidx in range(len(entries)):
                    kst = self._state(provider, kidx, model)
                    if not kst.disabled:
                        all_disabled = False
                        break
                if all_disabled:
                    self._model_disabled[(provider, model)] = True
                    logger.warning("[LLM] %s model %s permanently disabled across all keys (%s)", provider, model, reason[:120])
                else:
                    logger.warning("[LLM] %s key #%d disabled for model %s (%s); other keys remain active", provider, key_index, model, reason[:120])
                return

            backoff = min(self.MAX_BACKOFF, self.BASE_BACKOFF * (2 ** (st.failures - 1)))
            backoff *= random.uniform(0.75, 1.25)
            wait = retry_after if retry_after else backoff
            until = time.time() + max(1.0, wait)

            st.cooldown_until = until
            if kentry:
                kentry.cooldown_until = until

            grp = quota_group or self.key_group(provider, key_index)
            if "429" in reason or "quota" in reason.lower() or "rate" in reason.lower():
                self._group_cd[(provider, grp, model)] = until

            if provider == "gemini" and not permanent:
                try:
                    from app.services.gemini import rotator as _grot
                    _grot.mark_failure(key_index, model, retry_after, reason)
                except Exception:
                    pass

            keys = self.provider_keys(provider)
            masked = self.mask_key(keys[key_index]) if key_index < len(keys) else "?"
            logger.warning("[LLM] %s key#%d %s / %s cooled %.0fs (group=%s, %s)",
                           provider, key_index, masked, model, wait, grp, reason[:120])

    def mark_success(self, provider: str, key_index: int, model: str, tokens: int = 0):
        with self._lock:
            st = self._state(provider, key_index, model)
            st.failures = 0
            st.cooldown_until = 0.0
            st.last_error = ""
            st.requests += 1
            st.last_used = time.time()

            entries = self._keys_by_provider.get(provider, [])
            if key_index < len(entries):
                kentry = entries[key_index]
                kentry.failures = 0
                kentry.cooldown_until = 0.0
                kentry.last_error = ""
                kentry.requests_today += 1
                kentry.tokens_today += tokens
                kentry.last_used = time.time()
                _usage_tracker.record(provider, kentry.masked, est_tokens=tokens)

            if provider == "gemini":
                try:
                    from app.services.gemini import rotator as _grot
                    _grot.mark_success(key_index, model)
                except Exception:
                    pass

            keys = self.provider_keys(provider)
            if keys:
                self._rr[provider] = (key_index + 1) % len(keys)

    def reset(self):
        with self._lock:
            self._states.clear()
            self._group_cd.clear()
            self._model_disabled.clear()
            self._discovered.clear()
            self._discovered_at.clear()
            self._rr.clear()
            for k in self._keys:
                k.failures = 0
                k.cooldown_until = 0.0
                k.last_error = ""
                k.disabled = False
                k.status = "healthy"

    # -- Key Probing & Validation ------------------------------------------

    def probe_key(self, key_entry: KeyEntry, timeout: float = 8.0) -> tuple[str, str]:
        """
        Probe a single key once to verify access and health.
        Returns (classification, detail).
        Classifications: 'healthy' | 'rate_limited' | 'invalid' | 'no_access'
        """
        spec = PROVIDERS.get(key_entry.provider)
        if not spec:
            return "invalid", "unknown provider"

        key = key_entry.key
        try:
            if spec.kind == "gemini":
                url = f"{spec.base_url}/models?key={key}&pageSize=1"
                req = urllib.request.Request(url, headers={"User-Agent": "EduSense-Probe/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return "healthy", "200 OK"
            else:
                url = f"{spec.base_url}/models"
                req = urllib.request.Request(url, headers={
                    "Authorization": f"Bearer {key}",
                    "User-Agent": "EduSense-Probe/1.0"
                })
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return "healthy", "200 OK"
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                pass
            if exc.code in (401, 403) or "invalid" in body.lower() or "unauthorized" in body.lower():
                return "invalid", f"HTTP {exc.code}: {body[:100]}"
            if exc.code == 429 or "quota" in body.lower() or "rate" in body.lower():
                return "rate_limited", f"HTTP 429: {body[:100]}"
            if exc.code == 404:
                return "no_access", f"HTTP 404: {body[:100]}"
            return "healthy", f"HTTP {exc.code} (active)"
        except Exception as exc:
            return "untested", str(exc)[:100]

        return "healthy", "OK"

    def validate_all_keys(self, probe: bool = True) -> list[dict[str, Any]]:
        """
        Probe every key concurrently, classify status, disable bad keys.
        """
        self.reload_keys()
        with self._lock:
            entries = list(self._keys)

        results = []
        if probe:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                future_to_entry = {ex.submit(self.probe_key, e): e for e in entries}
                for f in concurrent.futures.as_completed(future_to_entry):
                    entry = future_to_entry[f]
                    try:
                        status, detail = f.result()
                        entry.status = status
                        entry.last_error = detail if status != "healthy" else ""
                        if status in ("invalid", "no_access"):
                            entry.disabled = True
                            logger.warning("[LLM] Disabled bad key %s (%s:%s): %s",
                                           entry.masked_last4, entry.provider, entry.label, detail)
                        elif status == "rate_limited":
                            entry.cooldown_until = time.time() + 60.0
                    except Exception as err:
                        entry.status = "untested"
                        entry.last_error = str(err)
        for entry in entries:
            results.append({
                "provider": entry.provider,
                "label": entry.label,
                "key_masked": entry.masked,
                "key_masked_last4": entry.masked_last4,
                "quota_group": entry.quota_group,
                "dedicated_features": sorted(list(entry.dedicated_features)),
                "status": entry.status,
                "disabled": entry.disabled,
                "requests_today": entry.requests_today,
                "last_error": entry.last_error,
            })
        return results

    # -- Status Report -----------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Comprehensive status for /api/admin/llm-status and diagnostics."""
        now = time.time()
        providers_out = []
        for pname, spec in PROVIDERS.items():
            keys = self.provider_keys(pname)
            if not keys and pname != "gemini":
                continue
            models_cfg = self.provider_models(pname)
            models_state = []
            entries = self._keys_by_provider.get(pname, [])
            for model in models_cfg:
                for idx in range(len(keys)):
                    st = self._states.get((pname, idx, model))
                    grp = self.key_group(pname, idx)
                    gb = self._group_blocked(pname, grp, model)
                    cd = max(0.0, (st.cooldown_until - now) if st else 0.0)
                    is_cooling = bool(st and st.cooldown_until > now) or gb > 0
                    kentry = entries[idx] if idx < len(entries) else None
                    models_state.append({
                        "key_index": idx,
                        "key_label": kentry.label if kentry else f"key_{idx+1}",
                        "key_masked": self.mask_key(keys[idx]),
                        "key_masked_last4": self.mask_last4(keys[idx]),
                        "quota_group": grp,
                        "model": model,
                        "cooling_down": is_cooling,
                        "cooldown_remaining_s": round(max(gb, cd), 1),
                        "consecutive_failures": st.failures if st else 0,
                        "disabled": bool((st and st.disabled) or (kentry and kentry.disabled) or self._model_disabled.get((pname, model))),
                        "requests": st.requests if st else 0,
                        "dedicated_features": sorted(list(kentry.dedicated_features)) if kentry else [],
                        "status": kentry.status if kentry else "healthy",
                        "last_error": st.last_error if st else "",
                    })

            providers_out.append({
                "provider": pname,
                "kind": spec.kind,
                "base_url": spec.base_url,
                "keys_total": len(keys),
                "keys_healthy": sum(1 for idx in range(len(keys)) if not (entries[idx].disabled if idx < len(entries) else False)),
                "quota_groups": sorted(list({self.key_group(pname, i) for i in range(len(keys))})),
                "models": models_state,
            })

        chains = {}
        for feature in ("video_script", "kb_chat", "quizzes", "flashcards", "exams", "reports", "question_bank", "general"):
            cands = self.candidates(feature)
            seen, pairs = set(), []
            for p, _, _, m in cands:
                pair = f"{p}:{m}"
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
            chains[feature] = pairs

        return {
            "providers": providers_out,
            "chains": chains,
            "usage_today": _usage_tracker.get_stats(),
        }


router = LLMRouter()


# ---------------------------------------------------------------------------
# HTTP Call Dispatchers (Single attempt each)
# ---------------------------------------------------------------------------

def _retry_after(headers) -> float | None:
    try:
        ra = headers.get("Retry-After") if headers else None
        if ra:
            return float(ra)
    except Exception:
        pass
    return None


def _call_openai_compat(spec: ProviderSpec, key: str, model: str, prompt: str,
                        temperature: float | None, max_output_tokens: int | None,
                        timeout: float) -> str:
    url = f"{spec.base_url}/chat/completions"
    body_dict: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        body_dict["temperature"] = temperature
    if max_output_tokens is not None:
        body_dict["max_tokens"] = max_output_tokens

    body = json.dumps(body_dict).encode("utf-8")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "EduSense/2.0 (+https://github.com/adel-noufal/Edusense)",
    }
    if spec.auth_style != "none":
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    choices = payload.get("choices") or []
    if not choices:
        raise GeminiError(GeminiError.INVALID_RESPONSE, f"{spec.name} returned no choices")
    text = (choices[0].get("message") or {}).get("content") or ""
    text = text.strip()
    if not text:
        finish = choices[0].get("finish_reason", "")
        if "content_filter" in str(finish).lower() or _is_safety_block(str(payload)[:500]):
            raise GeminiError(GeminiError.SAFETY_BLOCKED, "Response blocked by safety filters")
        raise GeminiError(GeminiError.INVALID_RESPONSE, f"{spec.name} returned an empty response")
    return text


def _call_gemini_once(key: str, model: str, prompt: str,
                      temperature: float | None, max_output_tokens: int | None,
                      timeout: float) -> str:
    spec = PROVIDERS["gemini"]
    url = f"{spec.base_url}/models/{model}:generateContent?key={key}"
    gen_cfg: dict[str, Any] = {}
    if temperature is not None:
        gen_cfg["temperature"] = temperature
    if max_output_tokens is not None:
        gen_cfg["maxOutputTokens"] = max_output_tokens

    body_dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if gen_cfg:
        body_dict["generationConfig"] = gen_cfg

    body = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "EduSense/2.0 (+https://github.com/adel-noufal/Edusense)"
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    cand = payload.get("candidates") or []
    if not cand:
        raise GeminiError(GeminiError.INVALID_RESPONSE, "Gemini returned no candidates")

    block_reason = cand[0].get("finishReason") or ""
    parts = cand[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        if "SAFETY" in block_reason.upper() or "BLOCK" in block_reason.upper():
            raise GeminiError(GeminiError.SAFETY_BLOCKED, "Response blocked by safety filters")
        raise GeminiError(GeminiError.INVALID_RESPONSE, "Gemini returned an empty response")
    return text


def _call_provider(spec: ProviderSpec, key: str, model: str, prompt: str,
                   temperature: float | None, max_output_tokens: int | None,
                   timeout: float) -> str:
    if spec.kind == "gemini":
        return _call_gemini_once(key, model, prompt, temperature, max_output_tokens, timeout)
    return _call_openai_compat(spec, key, model, prompt, temperature, max_output_tokens, timeout)


# ---------------------------------------------------------------------------
# Strict JSON Repair Helper
# ---------------------------------------------------------------------------

def _repair_json_syntax(raw_text: str) -> dict | list | None:
    """Attempt local syntax repair on malformed JSON before re-prompting."""
    if not raw_text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    m = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(fixed)
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Public Chat API
# ---------------------------------------------------------------------------

def chat(prompt: str, task_type: str = "general", model: str | None = None,
         temperature: float | None = None, max_output_tokens: int | None = None,
         timeout: float = 60.0, exclude_provider: str | None = None,
         touch_student_data: bool = False) -> str:
    """
    Generate text using best-fit routing across all configured providers & keys.
    """
    est_prompt_tokens = max(1, len(prompt) // 4)

    if max_output_tokens and max_output_tokens > 1500 and timeout < 120:
        timeout = 120.0
    elif max_output_tokens and max_output_tokens > 4000 and timeout < 240:
        timeout = 240.0

    cands = router.candidates(
        task_type=task_type,
        prompt_tokens=est_prompt_tokens,
        exclude_provider=exclude_provider,
        touch_student_data=touch_student_data
    )

    if model:
        preferred = [(p, i, k, m) for p, i, k, m in cands if m == model]
        rest = [(p, i, k, m) for p, i, k, m in cands if m != model]
        cands = preferred + rest

    now = time.time()
    viable = []
    with router._lock:
        for p, i, k, m in cands:
            st = router._states.get((p, i, m))
            if st and st.disabled:
                continue
            if st and st.cooldown_until > now:
                continue
            grp = router.key_group(p, i)
            if router._group_blocked(p, grp, m) > 0:
                continue
            viable.append((p, i, k, m))

    if not viable:
        raise GeminiError(GeminiError.QUOTA_EXHAUSTED,
                          "All configured LLM provider/key/model combinations are cooling down or disabled")

    last_error: GeminiError | None = None

    for p, i, k, m in viable:
        spec = PROVIDERS.get(p)
        if not spec:
            continue
        masked = router.mask_key(k)
        grp = router.key_group(p, i)
        t0 = time.time()
        try:
            text = _call_provider(spec, k, m, prompt, temperature, max_output_tokens, timeout)
            latency = time.time() - t0
            est_tokens = len(text) // 4
            router.mark_success(p, i, m, tokens=est_tokens)
            logger.info("[LLM] feature=%s provider=%s model=%s key=%s latency=%.2fs outcome=SUCCESS",
                        task_type, p, m, masked, latency)
            return text
        except urllib.error.HTTPError as exc:
            latency = time.time() - t0
            detail = ""
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                pass
            err_code, rotatable = _classify_http_error(exc.code, detail)
            retry_after = _retry_after(getattr(exc, "headers", None))
            err = GeminiError(err_code, f"{p} API error ({exc.code}): {detail[:200]}")
            last_error = err
            permanent = (exc.code in (404, 410)) or \
                        (exc.code == 400 and ("model" in detail.lower() and ("not found" in detail.lower() or "does not exist" in detail.lower() or "no longer available" in detail.lower())))
            router.mark_failure(p, i, m, retry_after, f"HTTP {exc.code}: {detail[:120]}",
                                permanent=permanent, quota_group=grp)
            logger.warning("[LLM] feature=%s provider=%s model=%s key=%s latency=%.2fs outcome=HTTP_%d rotatable=%s permanent=%s",
                           task_type, p, m, masked, latency, exc.code, rotatable, permanent)
            # Never raise a single provider's failure if other candidate providers/models exist in the chain
            continue
        except TimeoutError:
            latency = time.time() - t0
            router.mark_failure(p, i, m, None, "timeout", quota_group=grp)
            last_error = GeminiError(GeminiError.TIMEOUT, f"{p} request timed out")
            logger.warning("[LLM] feature=%s provider=%s model=%s key=%s latency=%.2fs outcome=TIMEOUT",
                           task_type, p, m, masked, latency)
            continue
        except urllib.error.URLError as exc:
            latency = time.time() - t0
            router.mark_failure(p, i, m, None, f"urlerror: {exc}", quota_group=grp)
            last_error = GeminiError(GeminiError.MODEL_UNAVAILABLE, f"{p} connection failed: {exc}")
            logger.warning("[LLM] feature=%s provider=%s model=%s key=%s latency=%.2fs outcome=URL_ERROR",
                           task_type, p, m, masked, latency)
            continue
        except GeminiError as exc:
            if exc.code in (GeminiError.SAFETY_BLOCKED, GeminiError.INVALID_REQUEST):
                raise
            router.mark_failure(p, i, m, None, exc.code, quota_group=grp)
            last_error = exc
            continue
        except Exception as exc:
            router.mark_failure(p, i, m, None, str(exc)[:120], quota_group=grp)
            last_error = GeminiError(GeminiError.UNKNOWN, f"{p} request failed: {exc}")
            continue

    if last_error:
        raise GeminiError(last_error.code,
                          f"All LLM provider/key/model combinations exhausted. Last: {last_error}")
    raise GeminiError(GeminiError.QUOTA_EXHAUSTED, "No usable LLM provider/key/model combination available")


def chat_json(prompt: str, task_type: str = "general", **kwargs) -> dict | list:
    """
    Generate and parse strict JSON with one repair attempt before rotating.
    """
    raw_response = chat(prompt, task_type=task_type, **kwargs)
    parsed = _extract_json(raw_response)
    if parsed is not None:
        return parsed

    repaired = _repair_json_syntax(raw_response)
    if repaired is not None:
        logger.info("[LLM] JSON syntax repair succeeded locally")
        return repaired

    try:
        repair_prompt = f"Fix this invalid JSON and return ONLY the raw valid JSON without markdown fences:\n{raw_response[:3000]}"
        fix_response = chat(repair_prompt, task_type="kb_chat", temperature=0.0, timeout=20.0)
        parsed = _extract_json(fix_response) or _repair_json_syntax(fix_response)
        if parsed is not None:
            logger.info("[LLM] JSON repair via LLM succeeded")
            return parsed
    except Exception as exc:
        logger.warning("[LLM] JSON repair prompt failed: %s", exc)

    raise GeminiError(GeminiError.INVALID_RESPONSE, "LLM response was not valid JSON after repair attempt")


def status() -> dict[str, Any]:
    return router.status()


def reset() -> None:
    router.reset()
