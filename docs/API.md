# EduSense API Documentation

Base URL: `http://localhost:8000/api`

## Authentication

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /users/me`

Use `Authorization: Bearer <token>` for protected endpoints.

## Users and Profiles

- `GET /users`
- `GET /users/students`
- `GET /users/profile`
- `PUT /users/profile`

## Sessions

- `GET /sessions`
- `POST /sessions`
- `PUT /sessions/{session_id}`
- `DELETE /sessions/{session_id}`
- `POST /sessions/{session_id}/join`
- `POST /sessions/{session_id}/start`
- `POST /sessions/{session_id}/end`

## Emotion Logs

- `POST /emotions/analyze`
- `POST /emotions`
- `GET /emotions/session/{session_id}`
- `GET /emotions/session/{session_id}/distribution`

## AI Agents

- `POST /ai/lessons`
- `POST /ai/quizzes`
- `GET /ai/engagement/{session_id}`
- `GET /ai/recommendations/{session_id}`
- `POST /ai/recommendations/{session_id}/decision`
- `POST /ai/videos`
- `GET /ai/videos`
- `DELETE /ai/videos/{video_id}`

## Reports and Feedback

- `GET /reports`
- `POST /reports/{session_id}`
- `POST /feedback`
