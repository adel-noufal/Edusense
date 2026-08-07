import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

/** Smooth enter animation on every route change. */
export default function PageTransition({ children }) {
  const location = useLocation()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(false)
    const frame = window.requestAnimationFrame(() => setVisible(true))
    window.scrollTo({ top: 0, left: 0, behavior: 'smooth' })
    return () => window.cancelAnimationFrame(frame)
  }, [location.pathname])

  return (
    <div key={location.pathname} className={`route-enter ${visible ? 'route-enter-visible' : ''}`}>
      {children}
    </div>
  )
}
