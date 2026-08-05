import base64
from collections import Counter
from datetime import datetime, timezone
import cv2
import numpy as np
from sqlalchemy.orm import Session
from app.agents.base import AgentResult, adk_agent
from app.models.models import EmotionLog

SUPPORTED_EMOTIONS = ["happy", "neutral", "sad", "angry", "surprise", "fear", "disgust"]

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
        emotion, confidence = self._detect(image)
        log = EmotionLog(
            session_id=session_id,
            student_id=student_id,
            emotion=emotion,
            confidence=confidence,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return AgentResult(
            self.name,
            {
                "id": log.id,
                "emotion": emotion,
                "confidence": confidence,
                "timestamp": log.timestamp.isoformat(),
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
        try:
            frame = self._decode_frame(image)

            # --- Primary: v7 PyTorch EfficientNet-B0 ---
            result = self._detect_pytorch(frame)
            if result is not None:
                self._active_backend = "pytorch_v7"
                return result

            # --- Fallback: DeepFace (TensorFlow) ---
            self._active_backend = "deepface"
            return self._detect_deepface(frame)

        except Exception:
            self._active_backend = "fallback"
            return "neutral", 0.64

    # ---------- frame helpers ----------

    @staticmethod
    def _decode_frame(image: str) -> np.ndarray:
        payload = image.split(",", 1)[1] if "," in image else image
        image_bytes = base64.b64decode(payload)
        return cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)

    # ---------- PyTorch v7 backend ----------

    def _detect_pytorch(self, frame: np.ndarray):
        """
        Load and run the v7 EfficientNet-B0 model.
        Returns (emotion, confidence) or None if torch/model unavailable.
        """
        try:
            from pathlib import Path
            import torch
            from torchvision import transforms, models
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
                probs = torch.softmax(logits, dim=1)[0]
                top_idx = int(torch.argmax(probs).item())
                emotion = V7_IDX_TO_CLASS.get(top_idx, "neutral").lower()
                confidence = float(probs[top_idx].item())

            return (
                emotion if emotion in SUPPORTED_EMOTIONS else "neutral",
                round(confidence, 3),
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
        from deepface import DeepFace

        result = DeepFace.analyze(
            frame, actions=["emotion"], enforce_detection=False
        )
        row = result[0] if isinstance(result, list) else result
        emotion = str(row.get("dominant_emotion", "neutral")).lower()
        scores = row.get("emotion", {})
        confidence = float(scores.get(emotion, 70)) / 100
        return (
            emotion if emotion in SUPPORTED_EMOTIONS else "neutral",
            round(confidence, 3),
        )
