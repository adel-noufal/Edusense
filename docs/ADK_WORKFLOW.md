# EduSense Multi-Agent System Workflows

```mermaid
sequenceDiagram
  autonumber
  participant S as Student
  participant E as Emotion Analysis Agent (v7 PyTorch)
  participant G as Student Engagement Agent
  participant R as Recommendation Agent
  participant L as Lesson Generation Agent
  participant Q as Quiz Generation Agent
  participant P as Report Generation Agent
  participant I as Instructor

  S->>E: Webcam frames during live session
  E->>E: v7 EfficientNet-B0 emotion classification (90.9% accuracy)
  E->>G: Emotion logs & aggregated distributions
  G->>R: Engagement score %, attention timeline & disengagement flags
  R->>L: Low engagement concepts & pedagogical recommendations
  R->>Q: Targeted reinforcement needs
  L->>P: Simplified lesson & visual slide explanations
  Q->>P: Adaptive MCQ / True-False knowledge checks
  P->>I: Executive PDF Report & Analytics Dashboard
  I->>L: Accept & deploy improved lesson/materials
```

---

## 👨‍🏫 Instructor Workflow
1. **Create & Schedule Session**: Set lesson topic, date, start time, and target student group.
2. **Monitor Live Dashboard**: Real-time webcam emotion feedback (Happy, Neutral, Sad, Surprised, Confused, Disengaged) displayed via interactive Recharts.
3. **Receive AI Recommendations**: Triggers pedagogical suggestions when engagement drops below threshold (<62%).
4. **Export Executive PDF Report**: Automated post-session PDF export via ReportLab summarizing class performance and reinforcement materials.

---

## 🎓 Student Workflow
1. **Join Classroom**: Access scheduled sessions and launch live room interface.
2. **Real-time Engagement Stream**: Webcam frames stream in background to emotion analysis engine.
3. **Adaptive AI Study Tools**: Access AI-generated flashcards, practice quizzes, and lesson slides.

