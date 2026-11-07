import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem('edusense_user') || 'null'))

  useEffect(() => {
    if (user) localStorage.setItem('edusense_user', JSON.stringify(user))
  }, [user])

  async function login(email, password) {
    const result = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    localStorage.setItem('edusense_token', result.access_token)
    setUser(result.user)
    return result.user
  }

  async function register(payload) {
    const result = await api('/auth/register', { method: 'POST', body: JSON.stringify(payload) })
    localStorage.setItem('edusense_token', result.access_token)
    setUser(result.user)
    return result.user
  }

  function logout() {
    localStorage.removeItem('edusense_token')
    localStorage.removeItem('edusense_user')
    setUser(null)
  }

  const value = useMemo(() => ({ user, login, register, logout }), [user])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) throw new Error('Auth context is unavailable')
  return context
}
