"""One real lesson run with the per-provider outcome printed (Addendum #13 batch 2).

    .venv/Scripts/python.exe scripts/lesson_provider_diagnostic.py [topic] [detail]

Prints: the routing chain, each provider's error, the wall time, and whether the
answer came from a model or from the template fallback.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

from app.agents.lesson_agent import LessonGenerationAgent  # noqa: E402
from app.schemas.schemas import LessonRequest  # noqa: E402
from app.services import llm  # noqa: E402


def main() -> int:
    topic = sys.argv[1] if len(sys.argv) > 1 else "Python variables and reassignment"
    detail = sys.argv[2] if len(sys.argv) > 2 else "Standard"

    print("\n=== ROUTING CHAIN (feature=lesson) ===")
    for provider, _idx, key, model in llm.router.candidates("lesson", prompt_tokens=2500):
        print(f"  {provider:<10} {model:<34} key={llm.router.mask_key(key)}")

    print(f"\n=== RUN: topic={topic!r} detail={detail} ===")
    t0 = time.time()
    result = LessonGenerationAgent().generate(
        LessonRequest(topic=topic, prompt="", detail_level=detail,
                      language="English", teaching_style="Interactive")
    )
    elapsed = round(time.time() - t0, 1)
    data = result.data
    sections = data.get("sections") or []
    words = [len(str(s.get("content", "")).split()) for s in sections]
    print(f"\nWALL_SECONDS {elapsed}")
    print(f"ANSWERED_BY {llm.last_used()}")
    print(f"SECTIONS {len(sections)} words_per_section {words}")
    print(f"TITLE {data.get('topic')}")
    print(f"UNVERIFIED {data.get('unverified')} sources={data.get('sources')}")

    print("\n=== PER-PROVIDER STATE (last error, cooldown) ===")
    now = time.time()
    for (provider, idx, model), state in sorted(llm.router._states.items()):
        cool = max(0.0, state.cooldown_until - now)
        print(f"  {provider:<10} key#{idx} {model:<34} failures={state.failures} "
              f"cooldown={cool:.0f}s last_error={state.last_error[:120]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
