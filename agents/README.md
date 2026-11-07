# EduSense Agents

The executable agent implementations live in `backend/app/agents`.

Each module declares a Google ADK-compatible agent and exposes a local Python class so EduSense runs offline:

- `emotion_agent.py`
- `engagement_agent.py`
- `recommendation_agent.py`
- `lesson_agent.py`
- `quiz_agent.py`
- `report_agent.py`
- `workflow.py`

The `EduSenseAgentWorkflow` class implements the intelligent feedback loop required by the capstone.
