import json
from collections import defaultdict

from app.agents.base import AgentResult, adk_agent
from app.core.config import get_settings
from app.services.gemini import generate_json_any

ADK_AGENT = adk_agent("recommendation_agent", "Analyze emotion and engagement reports and recommend instructional improvements.")

# Windows (minutes) used to locate low-engagement segments in the timeline
LOW_WINDOW_MINUTES = 5


def _low_engagement_windows(timeline: list[dict], threshold: float) -> list[dict]:
    """Bucket the attention timeline into LOW_WINDOW_MINUTES windows and
    return windows whose mean score is below `threshold`."""
    if not timeline:
        return []
    buckets: dict[int, list[float]] = defaultdict(list)
    base = None
    from datetime import datetime
    for point in timeline:
        try:
            ts = datetime.fromisoformat(str(point.get("timestamp", "")).replace("Z", "+00:00"))
        except Exception:
            continue
        if base is None:
            base = ts
        idx = int((ts - base).total_seconds() // (LOW_WINDOW_MINUTES * 60))
        buckets[idx].append(float(point.get("score", 0)))
    windows = []
    for idx in sorted(buckets):
        scores = buckets[idx]
        avg = sum(scores) / len(scores)
        if avg < threshold:
            windows.append({
                "minute_start": idx * LOW_WINDOW_MINUTES,
                "minute_end": (idx + 1) * LOW_WINDOW_MINUTES,
                "avg_score": round(avg, 1),
                "samples": len(scores),
            })
    return windows[:6]  # cap to keep prompt small


def _rule_based_recommendations(facts: dict, threshold: float) -> list[dict]:
    """Deterministic fallback: every item cites the computed fact behind it."""
    recs = []
    score = facts.get("engagement_percentage")
    dist = facts.get("emotion_distribution_pct") or {}
    windows = facts.get("low_engagement_windows") or []
    attended = facts.get("attended_minutes")

    if score is not None and score < threshold:
        recs.append({
            "text": "Slow down the lesson pace and pause after difficult concepts.",
            "evidence": f"Engagement averaged {score}% across {facts.get('emotion_samples', 0)} samples, below the {threshold}% threshold.",
        })
    if windows:
        w = windows[0]
        recs.append({
            "text": "Insert an interactive activity or quick poll during the weakest segment.",
            "evidence": f"Engagement dropped to {w['avg_score']}% around minute {w['minute_start']}-{w['minute_end']}.",
        })
    negative = {k: v for k, v in dist.items() if k in ("sad", "angry", "fear", "disgust") and v >= 15}
    if negative:
        top = max(negative.items(), key=lambda kv: kv[1])
        recs.append({
            "text": "Check for confusion or frustration and clarify the current topic.",
            "evidence": f"'{top[0].capitalize()}' emotion peaked at {top[1]}% of frames.",
        })
    if attended is not None and attended > 0 and score is not None and score >= threshold:
        recs.append({
            "text": "Maintain the current pace and add one challenge question.",
            "evidence": f"Engagement held at {score}% over {attended} attended minutes.",
        })
    return recs[:5]


class RecommendationAgent:
    name = "Recommendation Agent"

    def recommend(self, engagement: dict, emotions: dict, metrics: dict | None = None) -> AgentResult:
        settings = get_settings()
        threshold = settings.engagement_threshold
        score = engagement.get("engagement_percentage")
        has_data = bool(engagement.get("has_data")) or score is not None
        distribution = emotions.get("distribution", {}) or {}
        dominant = sorted(distribution.items(), key=lambda item: item[1], reverse=True)[:3]

        # â”€â”€ Deterministic facts (never LLM-generated) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        timeline = engagement.get("attention_timeline") or []
        windows = _low_engagement_windows(timeline, threshold)
        facts = {
            "engagement_percentage": score,
            "engagement_threshold": threshold,
            "emotion_samples": emotions.get("samples") or len(timeline),
            "emotion_distribution_pct": {k: v for k, v in distribution.items() if v},
            "dominant_emotions": [{"emotion": k, "pct": v} for k, v in dominant],
            "low_engagement_windows": windows,
            "participants": (metrics or {}).get("participants"),
            "attended_minutes": (metrics or {}).get("attended_minutes"),
            "sufficient_data": (metrics or {}).get("sufficient_data", has_data),
        }

        # Below data threshold -> honest empty state, no fabricated advice
        if facts["sufficient_data"] is False or not has_data:
            return AgentResult(self.name, {
                "score": score,
                "dominant_emotions": dominant,
                "recommendations": [],
                "rationale": "",
                "insufficient_data": True,
                "message": "Not enough session data to generate recommendations yet.",
                "facts": facts,
            })

        recs: list[dict] = []
        if score is not None:
            # Ask the LLM to phrase recommendations grounded ONLY in `facts`
            prompt = f"""You are an expert instructional designer. Write up to 4 short, specific
teaching recommendations for the session described by the JSON facts below.

RULES:
- Every recommendation MUST cite the evidence from the facts (quote the number/emotion/window).
- Do NOT invent data, students, or events not present in the facts.
- No generic filler like "engage students" without a cited reason.
- If the facts are insufficient for a recommendation, return fewer items.

Return ONLY valid JSON: {{"recommendations": [{{"text": "...", "evidence": "..."}}]}}

FACTS:
{json.dumps(facts, ensure_ascii=False)}
"""
            try:
                data = generate_json_any(prompt, task_type="report")
                items = data.get("recommendations") if isinstance(data, dict) else None
                if isinstance(items, list):
                    valid_emotions = set(facts["emotion_distribution_pct"])
                    for item in items[:5]:
                        if not isinstance(item, dict):
                            continue
                        text = str(item.get("text") or "").strip()
                        evidence = str(item.get("evidence") or "").strip()
                        if not text or not evidence:
                            continue  # schema validation: both fields required
                        # reject items whose evidence references emotions not in the data
                        ev_lower = evidence.lower()
                        bad_ref = any(
                            emo in ev_lower and emo not in valid_emotions
                            for emo in ("happy", "sad", "angry", "fear", "disgust", "surprise", "neutral")
                        )
                        if bad_ref:
                            continue
                        recs.append({"text": text, "evidence": evidence})
            except Exception as exc:
                print(f"[RecommendationAgent] LLM pass failed ({exc}); using rule-based fallback.")

        if not recs:
            recs = _rule_based_recommendations(facts, threshold)

        flat = [r["text"] for r in recs]
        evidence_map = {r["text"]: r["evidence"] for r in recs}
        return AgentResult(self.name, {
            "score": score,
            "dominant_emotions": dominant,
            "recommendations": flat,
            "recommendation_details": recs,
            "rationale": "; ".join(evidence_map.values())[:500],
            "insufficient_data": False,
            "facts": facts,
        })
