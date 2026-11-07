# EduSense Privacy Policy (DRAFT)

> **⚠️ LEGAL NOTICE**: This is a **DRAFT** policy document. The actual legal wording **must be reviewed by a qualified attorney** before production use, especially since minors are involved. Do not present this generated text as legally final.

**Effective Date**: 2026-11-07
**Version**: 1.0
**Last Updated**: 2026-11-07

---

## 1. Overview

EduSense ("we", "our", "us") is an AI-powered education platform providing adaptive learning, real-time emotion recognition, and intelligent assessment tools. This Privacy Policy explains what personal data we collect, how we use it, how long we retain it, and your rights regarding your data.

---

## 2. Data Controller

**EduSense AI Education Platform**
- Contact: privacy@edusense.example.com
- Author: Adel Mohamed Noufal

---

## 3. Categories of Personal Data Collected

### 3.1 Webcam Frames (Emotion Detection)
- **What**: Video frames captured from your webcam during live class sessions
- **Purpose**: Real-time facial emotion recognition (PyTorch v7 EfficientNet-B0) to help instructors gauge student engagement
- **Legal Basis**: Explicit consent (see Section 6)
- **Retention**: **End of session + 24 hours** — frames are automatically deleted 24 hours after the session ends
- **Access**: Instructors of the session, platform administrators

### 3.2 Webcam Frames (Quiz Anti-Cheat Monitoring)
- **What**: Video frames captured from your webcam during proctored quizzes
- **Purpose**: Anti-cheat monitoring — detects second devices, fullscreen exits, tab switches
- **Legal Basis**: Explicit consent (separate from emotion detection consent)
- **Retention**: **End of quiz attempt + 24 hours** — frames are automatically deleted 24 hours after the quiz attempt is submitted or auto-submitted
- **Access**: Instructor who created the quiz, platform administrators
- **Disclosure**: This is a **separate camera use** from emotion detection. Granting consent for emotion detection does NOT automatically grant consent for quiz anti-cheat monitoring.

### 3.3 Audio Data
- **What**: No audio is currently recorded or processed by the platform
- **Future Use**: If audio features are added, separate consent will be required

### 3.4 Quiz Answers & Assessment Data
- **What**: Answers submitted during quizzes, scores, per-question breakdown, time taken
- **Purpose**: Grading, progress tracking, adaptive learning recommendations
- **Retention**: Duration of enrollment + 1 academic year (configurable by institution)
- **Access**: Student, instructor of the session, platform administrators

### 3.5 Engagement Scores
- **What**: Aggregated emotion distributions, attention metrics, participation indicators
- **Purpose**: Instructor dashboards, session reports, adaptive content recommendations
- **Retention**: Duration of enrollment + 1 academic year
- **Access**: Instructor of the session, platform administrators

### 3.6 Chat Messages
- **What**: Messages sent in the educational chat (RAG + Web Search + LLM orchestration)
- **Purpose**: Conversation history, context for follow-up questions, audit trail
- **Retention**: Duration of enrollment + 1 academic year
- **Access**: Student (own messages), instructor of related session, platform administrators

### 3.7 Uploaded Resources
- **What**: Files uploaded by instructors (slides, PDFs, presentations) linked to sessions
- **Purpose**: Course materials, RAG knowledge base for AI generation
- **Retention**: Until explicitly deleted by uploading instructor or session deletion
- **Access**: Instructor who uploaded, students enrolled in the session, platform administrators

### 3.8 Account & Profile Data
- **What**: Name, email, role (student/instructor/admin), profile fields (phone, university, department, avatar)
- **Purpose**: Authentication, authorization, communication
- **Retention**: Until account deletion
- **Access**: Platform administrators, user themselves

---

## 4. Data Processing & Sharing

### 4.1 Internal Access (Role-Based)
| Role | Webcam Frames (Emotion) | Webcam Frames (Quiz) | Quiz Data | Engagement | Chat | Resources |
|------|------------------------|---------------------|-----------|------------|------|-----------|
| Student | Own session only | Own attempts only | Own attempts | Own scores | Own messages | Enrolled sessions |
| Instructor | Own sessions | Own quizzes | Own quizzes | Own sessions | Own sessions | Own uploads + enrolled |
| Admin | All | All | All | All | All | All |

### 4.2 AI Processing
- **Emotion Analysis**: PyTorch v7 EfficientNet-B0 model runs locally (on-premise or controlled cloud). Frames are NOT sent to third-party AI providers for emotion detection.
- **Quiz Generation / Lesson / Flashcards**: Uses multi-tier AI routing (Gemini 2.0 Flash → specialized local Ollama models). Prompt data may be sent to Google (Gemini) or local models. No webcam frames are sent to AI providers.
- **RAG Search**: Queries sent to embedding model (sentence-transformers) and ChromaDB vector store (local).

### 4.3 Third-Party Sharing
We do **not** sell personal data. Data may be shared with:
- **Google (Gemini API)**: For AI generation tasks (lessons, quizzes, flashcards) — only prompt text, no webcam frames or biometric data
- **Institutional Partners**: If you access EduSense through a school/university, aggregated analytics may be shared per institutional agreement

---

## 5. Data Retention & Deletion

| Data Category | Retention Period | Deletion Trigger |
|---------------|------------------|------------------|
| Webcam frames (emotion) | End of session + 24h | Automatic |
| Webcam frames (quiz anti-cheat) | End of attempt + 24h | Automatic |
| Quiz answers/scores | Enrollment + 1 year | Manual or account deletion |
| Engagement scores | Enrollment + 1 year | Manual or account deletion |
| Chat messages | Enrollment + 1 year | Manual or account deletion |
| Uploaded resources | Until deleted | Instructor action |
| Account/profile | Until deletion | User/admin action |

### 5.1 Automated Deletion
- Webcam frames are purged by a scheduled background job (runs hourly)
- Deletion is logged in audit trail

### 5.2 Manual Deletion Requests
**Students / Guardians** can request data deletion by:
1. **In-App**: Settings → Privacy → Request Data Deletion
2. **Email**: privacy@edusense.example.com with subject "Data Deletion Request"
3. **Instructor/Guardian Portal**: For minor accounts

**Response Timeline**: We will acknowledge within 48 hours and complete deletion within 30 days, per applicable law (GDPR Art. 17, CCPA §1798.105).

**Scope of Deletion**: All personal data except:
- Audit logs (retained for security/compliance, anonymized where possible)
- Aggregated anonymous analytics (cannot be linked to individual)

---

## 6. Consent Mechanism

### 6.1 Granular Consent
Consent is **purpose-specific** and **not bundled**:
- **Emotion Detection**: Webcam during live sessions for engagement analysis
- **Quiz Anti-Cheat**: Webcam during proctored quizzes for integrity monitoring

### 6.2 Consent Flow
1. **Before first camera use**: Consent screen presented with clear purpose description
2. **Explicit accept/decline**: No pre-checked boxes; separate buttons for each purpose
3. **Privacy Policy link**: Direct link to this document on consent screen
4. **Record kept**: Consent type, version, timestamp, IP address stored in audit log
5. **Withdrawal anytime**: Settings → Privacy → Withdraw Consent (immediately blocks camera access)

### 6.3 Declining Consent
**Declining webcam consent does NOT block access to the rest of the platform.**
- Without emotion detection consent: Can attend sessions, take quizzes (without camera), use chat, access materials
- Without quiz anti-cheat consent: Can take quizzes in non-proctored mode (instructor may require proctoring for graded assessments)

---

## 7. Rights of Data Subjects

You have the right to:
- **Access**: Request a copy of your personal data
- **Rectification**: Correct inaccurate data
- **Erasure**: Request deletion (Section 5.2)
- **Restriction**: Limit processing of your data
- **Portability**: Receive your data in a structured, commonly used format
- **Object**: Object to processing based on legitimate interests
- **Withdraw Consent**: At any time (Section 6.3)

**For Minors**: Parents/guardians may exercise these rights on behalf of children under 13 (or applicable age of digital consent in your jurisdiction).

---

## 8. Security Measures

- **Encryption**: TLS 1.3 in transit; AES-256 at rest for database
- **Access Control**: Role-based access control (RBAC), JWT authentication, audit logging
- **Frame Processing**: Webcam frames processed in memory; not persisted to disk beyond retention period
- **Minimal Collection**: Only frames necessary for stated purpose captured

---

## 9. International Transfers

If you access EduSense from outside the hosting jurisdiction, your data may be transferred to servers in other countries. We rely on:
- Standard Contractual Clauses (SCCs)
- Adequacy decisions where applicable
- Your explicit consent for specific transfers (e.g., Gemini API calls)

---

## 10. Children's Privacy (COPPA / GDPR-K)

- **Age Gate**: Users under 13 (or applicable age) require verifiable parental consent
- **Minor Accounts**: Flagged in system; enhanced protections apply
- **Data Minimization**: Only essential data collected for minors
- **Guardian Controls**: Guardians can review, export, delete minor's data
- **⚠️ FLAGGED FOR LEGAL REVIEW**: This section requires attorney review before launch

---

## 11. Changes to This Policy

We may update this policy. Material changes will be notified via:
- In-app banner (7 days before effective)
- Email to registered address
- Updated "Last Updated" date above

Continued use after effective date constitutes acceptance.

---

## 12. Contact

**Data Protection Officer**: Adel Mohamed Noufal
**Email**: privacy@edusense.example.com
**Address**: [Institutional Address]

---

## Appendix: Consent Versions

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-11-07 | Initial draft |