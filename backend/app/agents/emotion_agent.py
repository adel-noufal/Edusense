import os
import sys
import warnings

# Suppress TensorFlow and DeepFace noisy logs and deprecation spam
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["DEEPFACE_LOG_LEVEL"] = "40"
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import base64
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
from sqlalchemy.orm import Session
from app.agents.base import AgentResult, adk_agent
from app.models.models import EmotionLog

SUPPORTED_EMOTIONS = ["happy", "neutral", "sad", "angry", "surprise", "fear", "disgust"]

_CASCADE_PATH = (
    Path(__file__).resolve().parents[2] / "static" / "models"
    / "haarcascade_frontalface_default.xml"
)
_face_cascade = None
_mtcnn_detector = None

# v7 EfficientNet-B0 label ordering (standard AffectNet/FER+ alphabetical order)
# Confirmed from training: no class_to_idx stored in checkpoint → use standard ordering
V7_IDX_TO_CLASS = {
    0: "angry",
    1: "disgust",
    2: "fear",
    3: "happy",
    4: "neutral",
    5: "sad",
    6: "surprise",
}

ADK_AGENT = adk_agent(
    "emotion_analysis_agent",
    "Analyze webcam frames with custom v7 PyTorch EfficientNet-B0 (90.9% accuracy) and store emotion logs. Falls back to DeepFace if model is unavailable.",
)


class EmotionAnalysisAgent:
    """
    Emotion Analysis Agent — EduSense v7.

    Primary backend: custom-trained EfficientNet-B0 PyTorch model (v7, 90.9% overall accuracy).
      - angry:   88.6%  (n=1210)
      - disgust: 94.7%  (n=226)
      - fear:    87.3%  (n=1185)
      - happy:   94.1%  (n=715)
      - neutral: 95.5%  (n=378)
      - sad:     94.3%  (n=297)
      - surprise:96.4%  (n=193)

    Fallback: DeepFace (TensorFlow) when model weights are not found.
    """

    name = "Emotion Analysis Agent"

    # ---------- public API ----------

    def analyze_frame(
        self, db: Session, session_id: int, student_id: int, image: str
    ) -> AgentResult:
        detail = self._detect_detailed(image)
        emotion = detail.get("emotion") or "unknown"
        confidence = float(detail.get("confidence") or 0.0)

        # Only persist frames where a usable face was actually classified —
        # "no face" / low-quality frames must not pollute session distributions.
        log = None
        if detail.get("face_detected"):
            log = EmotionLog(
                session_id=session_id,
                student_id=student_id,
                emotion=emotion,
                confidence=confidence,
            )
            db.add(log)
        try:
            from app.models.models import SessionRegistration
            reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=student_id).first()
            if reg:
                now_ts = datetime.now(timezone.utc)
                if not getattr(reg, "joined_at", None):
                    reg.joined_at = now_ts
                reg.left_at = now_ts
                reg.attended = True
        except Exception:
            pass
        db.commit()
        if log is not None:
            db.refresh(log)
        return AgentResult(
            self.name,
            {
                "id": log.id if log is not None else None,
                "emotion": emotion,
                "confidence": confidence,
                "face_detected": bool(detail.get("face_detected")),
                "hint": detail.get("hint"),
                "top_emotions": detail.get("top_emotions"),
                "timestamp": log.timestamp.isoformat() if log is not None else datetime.now(timezone.utc).isoformat(),
                "backend": getattr(self, "_active_backend", "unknown"),
            },
        )

    def distributions(self, db: Session, session_id: int) -> AgentResult:
        logs = db.query(EmotionLog).filter(EmotionLog.session_id == session_id).all()
        total = max(len(logs), 1)
        counts = Counter(log.emotion for log in logs)
        data = {
            emotion: round(counts.get(emotion, 0) * 100 / total, 2)
            for emotion in SUPPORTED_EMOTIONS
        }
        return AgentResult(
            self.name,
            {
                "session_id": session_id,
                "distribution": data,
                "samples": len(logs),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ---------- internal detection ----------

    def _detect(self, image: str) -> tuple[str, float]:
        """Legacy tuple API — kept for callers that only need (emotion, conf)."""
        detail = self._detect_detailed(image)
        if not detail.get("face_detected"):
            return "unknown", 0.0
        return detail.get("emotion") or "neutral", float(detail.get("confidence") or 0.0)

    def _detect_detailed(self, image: str) -> dict:
        """
        Full detection pipeline: decode -> face detect -> crop -> classify.
        Returns a dict; never fabricates a confident 'neutral' on failure.
        """
        base = {
            "emotion": None, "confidence": 0.0, "top_emotions": [],
            "face_detected": False, "hint": None,
        }
        try:
            frame = self._decode_frame(image)
            if frame is None:
                return {**base, "hint": "bad_image"}

            crop, hint = self._find_face(frame)
            if crop is None or crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
                return {**base, "hint": hint or "no_face"}

            # Face found — classify the cropped face only.
            result = self._detect_pytorch_full(crop)
            if result is not None:
                emotion, confidence, probs = result
                self._active_backend = "pytorch_v7"
            else:
                self._active_backend = "deepface"
                emotion, confidence = self._detect_deepface(crop)
                probs = {emotion: confidence}

            if emotion not in SUPPORTED_EMOTIONS:
                emotion = "neutral"
            top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
            return {
                "emotion": emotion,
                "confidence": round(confidence, 4),
                "top_emotions": [{"emotion": e, "confidence": round(float(c), 4)} for e, c in top],
                "face_detected": True,
                "hint": hint,
            }
        except Exception:
            self._active_backend = "fallback"
            return {**base, "hint": "detection_error"}

    def _find_face(self, frame: np.ndarray):
        """
        Detect the largest frontal face, crop with padding.
        Returns (crop_bgr, quality_hint) — crop is None when no usable face.
        Detectors tried in order: MTCNN (accurate, bundled), OpenCV Haar
        (when the cv2 build ships cascades), else full-frame fallback.
        """
        global _face_cascade, _mtcnn_detector
        try:
            faces = None  # list of (x, y, w, h) in BGR-frame coords

            # --- MTCNN (primary; works on RGB) ---
            try:
                if _mtcnn_detector is None:
                    from mtcnn import MTCNN
                    _mtcnn_detector = MTCNN()
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                detections = _mtcnn_detector.detect_faces(rgb)
                boxes = [d["box"] for d in detections if d.get("confidence", 0) > 0.5]
                if boxes:
                    faces = [(int(x), int(y), int(w), int(h)) for x, y, w, h in boxes]
            except Exception:
                faces = None

            # --- OpenCV Haar fallback ---
            if faces is None:
                if _face_cascade is None:
                    if not _CASCADE_PATH.exists() or not hasattr(cv2, "CascadeClassifier"):
                        return None, "no_face"  # no detector -> honest no-face, never guess
                    _face_cascade = cv2.CascadeClassifier(str(_CASCADE_PATH))
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                raw = _face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5,
                    minSize=(int(frame.shape[1] * 0.08), int(frame.shape[0] * 0.08)),
                )
                faces = [tuple(map(int, f)) for f in raw] if len(raw) else []

            if not faces:
                return None, "no_face"

            # Largest face by area
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            pad = int(0.25 * max(w, h))
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1 = min(frame.shape[1], x + w + pad)
            y1 = min(frame.shape[0], y + h + pad)
            crop = frame[y0:y1, x0:x1]
            if crop is None or crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
                return None, "no_face"

            # Quality gates -> specific hint instead of a guess
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            brightness = float(gray_crop.mean())
            if brightness < 45:
                return crop, "too_dark"
            if brightness > 225:
                return crop, "too_bright"
            if w < 60:
                return crop, "too_small"
            blur = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
            if blur < 30:
                return crop, "blurry"
            return crop, None
        except Exception:
            return None, "detection_error"

    # ---------- frame helpers ----------

    @staticmethod
    def _decode_frame(image: str) -> np.ndarray:
        try:
            if not image:
                return None
            payload = image.split(",", 1)[1] if "," in image else image
            image_bytes = base64.b64decode(payload)
            if not image_bytes:
                return None
            return cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            return None

    # ---------- PyTorch v7 backend ----------

    def _detect_pytorch(self, frame: np.ndarray):
        """
        Load and run the v7 EfficientNet-B0 model.
        Returns (emotion, confidence) or None if torch/model unavailable.
        """
        full = self._detect_pytorch_full(frame)
        if full is None:
            return None
        return full[0], full[1]

    def _detect_pytorch_full(self, frame: np.ndarray):
        """Returns (emotion, confidence, {label: prob}) or None."""
        try:
            import torch
            from PIL import Image

            backend_root = Path(__file__).resolve().parents[2]
            project_root = backend_root.parent

            # Search canonical location first, then project root (convenience)
            candidates = [
                backend_root / "static" / "models" / "emotion_model.pth",
                project_root / "emotion_model_v7.pth",
                project_root / "emotion_model.pth",
            ]
            model_path = next((p for p in candidates if p.exists()), None)
            if model_path is None:
                return None

            # Cache model in instance to avoid reloading every frame
            if not hasattr(self, "_pytorch_model"):
                self._pytorch_model, self._pytorch_tf = self._load_pytorch_model(
                    str(model_path)
                )

            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            tensor = self._pytorch_tf(pil_img).unsqueeze(0)

            with torch.no_grad():
                logits = self._pytorch_model(tensor)
                probs_t = torch.softmax(logits, dim=1)[0]
                top_idx = int(torch.argmax(probs_t).item())
                emotion = V7_IDX_TO_CLASS.get(top_idx, "neutral").lower()
                confidence = float(probs_t[top_idx].item())
                probs = {
                    V7_IDX_TO_CLASS[i]: float(probs_t[i].item())
                    for i in range(len(V7_IDX_TO_CLASS))
                }

            return (
                emotion if emotion in SUPPORTED_EMOTIONS else "neutral",
                round(confidence, 3),
                probs,
            )

        except ImportError:
            # torch / torchvision not installed in this environment
            return None
        except Exception:
            return None

    @staticmethod
    def _load_pytorch_model(model_path: str):
        """Load EfficientNet-B0 checkpoint and preprocessing transform."""
        import torch
        from torchvision import transforms, models

        checkpoint = torch.load(model_path, map_location="cpu")

        # v7 checkpoint stores only 'state_dict' (no class_to_idx)
        state_dict = (
            checkpoint.get("state_dict")
            or checkpoint.get("model_state_dict")
            or checkpoint  # bare state dict
        )

        num_classes = len(V7_IDX_TO_CLASS)
        model = models.efficientnet_b0(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = torch.nn.Linear(in_features, num_classes)
        model.load_state_dict(state_dict, strict=True)
        model.eval()

        tf = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )
        return model, tf

    # ---------- DeepFace fallback backend ----------

    @staticmethod
    def _detect_deepface(frame: np.ndarray) -> tuple[str, float]:
        if frame is None or frame.size == 0 or frame.shape[0] < 20 or frame.shape[1] < 20:
            return "neutral", 0.0

        from deepface import DeepFace

        result = DeepFace.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False,
            detector_backend="skip",
        )
        row = result[0] if isinstance(result, list) else result
        emotion = str(row.get("dominant_emotion", "neutral")).lower()
        scores = row.get("emotion", {})
        confidence = float(scores.get(emotion, 70)) / 100
        return (
            emotion if emotion in SUPPORTED_EMOTIONS else "neutral",
            round(confidence, 3),
        )
