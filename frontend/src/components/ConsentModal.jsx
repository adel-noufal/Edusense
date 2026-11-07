import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'

const CONSENT_INFO = {
  emotion_detection: {
    title: 'Emotion Detection (Live Sessions)',
    description: (
      <>
        <p>During live class sessions, EduSense uses your webcam to analyze facial expressions in real-time (using a PyTorch EfficientNet-B0 model running locally). This helps instructors understand class engagement levels.</p>
        <ul>
          <li><strong>What's captured:</strong> Webcam video frames (face only, processed in real-time)</li>
          <li><strong>Purpose:</strong> Emotion classification (happy, neutral, sad, angry, surprise, fear, disgust) for engagement analytics</li>
          <li><strong>Retention:</strong> Frames are automatically deleted <strong>24 hours after the session ends</strong></li>
          <li><strong>Access:</strong> Only the session instructor and platform administrators</li>
          <li><strong>AI Processing:</strong> Runs locally on our servers — frames are NOT sent to third-party AI providers</li>
        </ul>
      </>
    ),
  },
  quiz_anti_cheat: {
    title: 'Quiz Anti-Cheat Camera Monitoring',
    description: (
      <>
        <p>During proctored quizzes, EduSense uses your webcam to monitor for academic integrity violations. This is a <strong>separate camera use</strong> from emotion detection.</p>
        <ul>
          <li><strong>What's captured:</strong> Webcam video frames during the quiz attempt</li>
          <li><strong>Purpose:</strong> Detect second devices (phones), fullscreen exits, tab switches, and other violations</li>
          <li><strong>Retention:</strong> Frames are automatically deleted <strong>24 hours after the quiz attempt is submitted</strong></li>
          <li><strong>Access:</strong> Only the quiz instructor and platform administrators</li>
          <li><strong>Violations:</strong> If a violation is detected, the attempt is auto-locked and the instructor must explicitly approve re-entry</li>
        </ul>
      </>
    ),
  },
}

const PRIVACY_POLICY_URL = '/PRIVACY_POLICY.md'

export function ConsentModal({
  isOpen,
  onClose,
  consentType,
  onAccept,
  onDecline,
}) {
  const { hasConsent } = useAuth()
  const [accepted, setAccepted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const info = CONSENT_INFO[consentType] || { title: 'Camera Access', description: '' }

  // Auto-close if consent already given
  useEffect(() => {
    if (isOpen && hasConsent(consentType)) {
      onClose()
    }
  }, [isOpen, consentType, hasConsent, onClose])

  async function handleAccept() {
    if (!accepted) return
    setLoading(true)
    setError(null)
    try {
      await onAccept(consentType)
      onClose()
    } catch (e) {
      setError(e.message || 'Failed to save consent. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  function handleDecline() {
    onDecline(consentType)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="consent-modal-overlay" onClick={handleDecline} role="dialog" aria-modal="true" aria-labelledby="consent-title">
      <div className="consent-modal" onClick={e => e.stopPropagation()}>
        <div className="consent-modal-header">
          <h2 id="consent-title">Camera Access Consent Required</h2>
          <p className="consent-subtitle">{info.title}</p>
        </div>

        <div className="consent-modal-body">
          <div className="consent-description">
            {info.description}
          </div>

          <div className="consent-policy-link">
            <a href={PRIVACY_POLICY_URL} target="_blank" rel="noopener noreferrer">
              📄 Read our full Privacy Policy
            </a>
            <p className="consent-note">
              This consent is <strong>specific to {info.title.toLowerCase()}</strong>.
              You can grant or decline each type independently.
            </p>
          </div>

          <label className="consent-checkbox">
            <input
              type="checkbox"
              checked={accepted}
              onChange={e => setAccepted(e.target.checked)}
              disabled={loading}
              required
            />
            <span>I understand the above and consent to {info.title.toLowerCase()}</span>
          </label>

          {error && <div className="consent-error" role="alert">{error}</div>}
        </div>

        <div className="consent-modal-footer">
          <button
            className="btn btn-secondary"
            onClick={handleDecline}
            disabled={loading}
          >
            Decline — Continue Without Camera
          </button>
          <button
            className="btn btn-primary"
            onClick={handleAccept}
            disabled={loading || !accepted}
          >
            {loading ? 'Saving...' : 'Accept & Enable Camera'}
          </button>
        </div>

        <p className="consent-footer-note">
          Declining does <strong>not</strong> block access to the rest of EduSense.
          You can still attend sessions, take quizzes (without camera), use chat, and access all materials.
          Consent can be granted later in Settings → Privacy.
        </p>
      </div>
    </div>
  )
}