# ADK Multi-Agent Workflow

```mermaid
sequenceDiagram
  participant S as Student
  participant E as Emotion Analysis Agent
  participant G as Student Engagement Agent
  participant R as Recommendation Agent
  participant L as Lesson Generation Agent
  participant Q as Quiz Generation Agent
  participant P as Report Generation Agent
  participant I as Instructor

  S->>E: Webcam frames during session
  E->>E: DeepFace emotion detection
  E->>G: Emotion logs and distributions
  G->>R: Engagement, attention, participation
  R->>L: Low engagement concepts and teaching issues
  R->>Q: Reinforcement needs
  L->>P: Improved lesson and visual explanations
  Q->>P: Knowledge checks
  P->>I: Report, recommendations, PDF
  I->>L: Accept and generate improved lesson/video
```

## Agents

1. Emotion Analysis Agent: webcam frames, DeepFace, emotion logs, distributions.
2. Student Engagement Agent: engagement score, attention timeline, disengagement detection.
3. Recommendation Agent: teaching recommendations from engagement and emotion reports.
4. Lesson Generation Agent: outlines, scripts, objectives, slides, images, diagrams.
5. Quiz Generation Agent: MCQ, true/false, short-answer, answers, difficulty.
6. Report Generation Agent: summaries, analytics, PDF export.
