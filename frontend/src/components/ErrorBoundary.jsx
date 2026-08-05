import { Component } from 'react'
import { Link } from 'react-router-dom'
import { translate } from '../i18n/translations'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    const lang = localStorage.getItem('edusense_lang') || 'en'
    const t = (key) => translate(lang, key)
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 dark:bg-slate-950">
          <div className="panel max-w-lg space-y-4">
            <h1 className="text-xl font-black text-red-600">{t('error.somethingWrong')}</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {this.state.error.message || t('error.somethingWrong')}
            </p>
            <div className="flex gap-3">
              <button type="button" className="btn-primary" onClick={() => window.location.reload()}>{t('error.reload')}</button>
              <Link className="btn-soft" to="/">{t('error.goHome')}</Link>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
