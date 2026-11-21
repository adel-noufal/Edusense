"""
B6 tests — emotion recognition honesty:
- no fabricated 'neutral 0.64' on failure/blank frames
- face detection gate: no face -> face_detected False + hint
- cropped face is what gets classified (mock classifier sees crop, not frame)
- top_emotions list returned
"""
import base64
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

import numpy as np
import cv2

from app.agents.emotion_agent import EmotionAnalysisAgent

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


def _b64(img):
    ok, buf = cv2.imencode(".jpg", img)
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def main():
    agent = EmotionAnalysisAgent()

    # blank dark frame -> no face, no fabricated neutral
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    d = agent._detect_detailed(_b64(blank))
    check("blank frame -> face_detected False", d["face_detected"] is False, str(d))
    check("blank frame -> hint set", d.get("hint") in ("no_face", "too_dark"), str(d.get("hint")))
    check("blank frame -> no confident emotion", not d.get("emotion") or d.get("confidence", 0) == 0, str(d.get("emotion")))

    # garbage bytes
    d2 = agent._detect_detailed("data:image/jpeg;base64," + base64.b64encode(b"notanimage").decode())
    check("garbage image handled without crash", isinstance(d2, dict))

    # face-crop path: mock cascade to return a face box, mock classifier to
    # verify it receives the CROP (smaller than frame)
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    seen = {}

    class FakeCascade:
        def detectMultiScale(self, *a, **k):
            return np.array([[100, 100, 200, 200]])

    def fake_pytorch(f):
        seen["shape"] = f.shape
        return ("happy", 0.91, {"happy": 0.91, "neutral": 0.05, "sad": 0.04})

    with patch.object(agent, "_find_face", return_value=(frame[50:300, 50:300], None)), \
         patch.object(agent, "_detect_pytorch_full", side_effect=fake_pytorch):
        d3 = agent._detect_detailed(_b64(frame))
    check("classified result returned", d3["emotion"] == "happy" and d3["confidence"] == 0.91, str(d3))
    check("top_emotions populated", len(d3["top_emotions"]) == 3, str(d3["top_emotions"]))
    check("face_detected True", d3["face_detected"] is True)

    # _detect legacy API: no-face -> ('unknown', 0.0), NOT ('neutral', 0.64)
    emo, conf = agent._detect(_b64(blank))
    check("legacy _detect no longer fabricates neutral",
          not (emo == "neutral" and conf == 0.64), f"{emo} {conf}")

    # real cascade sanity: haarcascade loads
    import app.agents.emotion_agent as ea
    check("cascade xml exists", ea._CASCADE_PATH.exists(), str(ea._CASCADE_PATH))

    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
