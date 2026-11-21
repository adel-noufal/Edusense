# EduSense Multi-Agent System Workflows

ðŸ‘¤ **Author:** [Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
ðŸ”— **LinkedIn:** [https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)
ðŸ“¦ **Repository:** [https://github.com/adel-noufal/Edusense](https://github.com/adel-noufal/Edusense)

---

## âš¡ Smart Multi-Tier AI Provider Task Router Diagram

```
                       â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                       â”‚          AI Agent Request           â”‚
                       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                          â”‚
                        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                        â”‚ ðŸŒ Gemini 2.0 Flash (Online API)  â”‚
                        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                          â”‚  (If Offline / Connection Fails)
                        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                        â”‚ ðŸ¦™ Specialized Local Ollama LLMs  â”‚
                        â”‚ â€¢ Translation -> Qwen 2.5 (7B)    â”‚
                        â”‚ â€¢ Lessons     -> Mistral (7B)     â”‚
                        â”‚ â€¢ Quizzes     -> Llama 3.1 (8B)   â”‚
                        â”‚ â€¢ Flashcards  -> Llama 3.2 (3B)   â”‚
                        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                          â”‚  (If Ollama Unreachable)
                        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                        â”‚ âš™ï¸ Built-in Local Templates        â”‚
                        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

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

## ðŸ‘¨â€ðŸ« Instructor Workflow
1. **Create & Schedule Session**: Set lesson topic, date, start time, and target student group.
2. **Monitor Live Dashboard**: Real-time webcam emotion feedback (Happy, Neutral, Sad, Surprised, Confused, Disengaged) displayed via interactive Recharts.
3. **Receive AI Recommendations**: Triggers pedagogical suggestions when engagement drops below threshold (<62%).
4. **Export Executive PDF Report**: Automated post-session PDF export via ReportLab summarizing class performance and reinforcement materials.

---

## ðŸŽ“ Student Workflow
1. **Join Classroom**: Access scheduled sessions and launch live room interface.
2. **Real-time Engagement Stream**: Webcam frames stream in background to emotion analysis engine.
3. **Adaptive AI Study Tools**: Access AI-generated flashcards, practice quizzes, and lesson slides.
