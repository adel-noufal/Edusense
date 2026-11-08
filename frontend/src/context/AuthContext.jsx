import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react'
import { api } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem('edusense_user') || 'null'))
  const [consents, setConsents] = useState(() => JSON.parse(localStorage.getItem('edusense_consents') || '{}'))

  useEffect(() => {
    if (user) localStorage.setItem('edusense_user', JSON.stringify(user))
  }, [user])

  useEffect(() => {
    localStorage.setItem('edusense_consents', JSON.stringify(consents))
  }, [consents])

  // Sync fresh user information on load
  useEffect(() => {
    const token = localStorage.getItem('edusense_token')
    if (token) {
      api('/users/me')
        .then((freshUser) => {
          if (freshUser && freshUser.id) {
            setUser(freshUser)
            localStorage.setItem('edusense_user', JSON.stringify(freshUser))
          }
        })
        .catch(() => {})
    }
  }, [])

  function updateUser(partial) {
    setUser((prev) => {
      const next = { ...prev, ...partial }
      localStorage.setItem('edusense_user', JSON.stringify(next))
      return next
    })
  }

  async function login(email, password) {
    const result = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    localStorage.setItem('edusense_token', result.access_token)
    setUser(result.user)
    // Fetch consents after login
    await fetchConsents()
    return result.user
  }

  async function register(payload) {
    const result = await api('/auth/register', { method: 'POST', body: JSON.stringify(payload) })
    localStorage.setItem('edusense_token', result.access_token)
    setUser(result.user)
    return result.user
  }

  async function fetchConsents() {
    try {
      const data = await api('/emotions/consent/list')
      const consentMap = {}
      data.forEach(c => {
        consentMap[c.consent_type] = {
          given: c.given,
          version: c.version,
          timestamp: c.timestamp,
          withdrawn_at: c.withdrawn_at,
        }
      })
      setConsents(consentMap)
    } catch (e) {
      console.warn('Failed to fetch consents:', e)
      setConsents({})
    }
  }

  async function giveConsent(consentType, version = '1.0') {
    await api('/emotions/consent/give', { method: 'POST', body: JSON.stringify({ consent_type: consentType, version }) })
    await fetchConsents()
  }

  async function withdrawConsent(consentType) {
    await api(`/emotions/consent/withdraw/${consentType}`, { method: 'POST' })
    await fetchConsents()
  }

  function hasConsent(consentType) {
    const c = consents[consentType]
    return c && c.given && !c.withdrawn_at
  }

  function logout() {
    localStorage.removeItem('edusense_token')
    localStorage.removeItem('edusense_user')
    localStorage.removeItem('edusense_consents')
    setUser(null)
    setConsents({})
  }

  const value = useMemo(() => ({
    user,
    consents,
    login,
    register,
    logout,
    updateUser,
    fetchConsents,
    giveConsent,
    withdrawConsent,
    hasConsent,
  }), [user, consents])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) throw new Error('Auth context is unavailable')
  return context
}
