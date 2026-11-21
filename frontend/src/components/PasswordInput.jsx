import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

export default function PasswordInput({
  value,
  onChange,
  placeholder,
  id,
  name,
  required,
  className = '',
  autoComplete,
  disabled,
  'aria-label': ariaLabel,
}) {
  const [show, setShow] = useState(false)
  const { isRtl } = useLanguage()

  return (
    <div className="relative w-full">
      <input
        type={show ? 'text' : 'password'}
        id={id}
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        autoComplete={autoComplete}
        disabled={disabled}
        aria-label={ariaLabel || placeholder || 'Password'}
        className={`input w-full ${isRtl ? 'pl-10 pr-3.5' : 'pr-10 pl-3.5'} ${className}`}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setShow(!show)}
        aria-label={show ? 'Hide password' : 'Show password'}
        className={`absolute top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition ${
          isRtl ? 'left-2.5' : 'right-2.5'
        }`}
      >
        {show ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  )
}
