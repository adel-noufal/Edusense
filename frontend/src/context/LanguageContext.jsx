import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { translate } from '../i18n/translations'

const LanguageContext = createContext(null)

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('edusense_lang') || 'en')

  useEffect(() => {
    localStorage.setItem('edusense_lang', lang)
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
  }, [lang])

  const value = useMemo(() => ({
    lang,
    isRtl: lang === 'ar',
    setLang,
    toggleLang: () => setLang((current) => (current === 'ar' ? 'en' : 'ar')),
    t: (key) => translate(lang, key),
  }), [lang])

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) throw new Error('Language context is unavailable')
  return context
}
