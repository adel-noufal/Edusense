---
# Hugging Face Model Card — EduSense v7 Emotion Model

language: en
license: mit
tags:
  - image-classification
  - emotion-recognition
  - pytorch
  - efficientnet
  - education
  - computer-vision
metrics:
  - accuracy
model-index:
  - name: emotion_model_v7
    results:
      - task:
          type: image-classification
        metrics:
          - type: accuracy
            value: 0.909
            name: Top-1 Accuracy (7-class)
---

# 🎭 EduSense Emotion Model v7

[![EduSense](https://img.shields.io/badge/Project-EduSense-blue)](https://github.com/adel-noufal/Edusense)
[![Author](https://img.shields.io/badge/Author-Adel_Mohamed_Noufal-0A66C2?logo=linkedin)](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
[![Accuracy](https://img.shields.io/badge/Accuracy-90.9%25-brightgreen)]()
[![PyTorch](https://img.shields.io/badge/PyTorch-EfficientNet--B0-EE4C2C?logo=pytorch)]()

## 📝 Model Description

**EduSense Emotion Model v7** is a custom-trained PyTorch image classification model based on the **EfficientNet-B0** architecture. It classifies 7 facial emotions from real-time webcam frames captured during online educational sessions.

### Architecture

| Component | Details |
|---|---|
| Base Model | `efficientnet_b0` (ImageNet pretrained) |
| Final Layer | `nn.Linear(1280 → 7)` |
| Input Size | `224×224 RGB` |
| Normalization | `mean=[0.485, 0.456, 0.406]`, `std=[0.229, 0.224, 0.225]` |
| Training | Fine-tuned on merged FER2013 + AffectNet subset |
| Accuracy | **90.9% top-1** on the 7-class held-out test set |
| Inference | CPU-only, ~80ms per frame on a modern laptop |

### Emotion Classes

```
0 → angry
1 → disgust
2 → fear
3 → happy
4 → neutral
5 → sad
6 → surprise
```

## 🚀 Usage

```python
import torch
import torchvision.transforms as transforms
from torchvision.models import efficientnet_b0
from PIL import Image

# Load model
model = efficientnet_b0(weights=None)
model.classifier[1] = torch.nn.Linear(1280, 7)
model.load_state_dict(torch.load("emotion_model_v7.pth", map_location="cpu"))
model.eval()

# Preprocessing
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

CLASSES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

# Inference
img = Image.open("face.jpg").convert("RGB")
tensor = transform(img).unsqueeze(0)
with torch.no_grad():
    logits = model(tensor)
probs = torch.softmax(logits, dim=1)
emotion = CLASSES[probs.argmax().item()]
confidence = probs.max().item()
print(f"{emotion} ({confidence:.1%})")
```

## 🔗 Integration

This model is integrated into the [EduSense](https://github.com/adel-noufal/Edusense) platform via `backend/app/agents/emotion_agent.py`. It falls back to [DeepFace](https://github.com/serengil/deepface) automatically if PyTorch is unavailable.

## 📄 License

MIT — see [LICENSE](https://github.com/adel-noufal/Edusense/blob/main/LICENSE)

## 👤 Author

**Adel Mohamed Noufal** — [LinkedIn](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/) · [GitHub](https://github.com/adel-noufal)
