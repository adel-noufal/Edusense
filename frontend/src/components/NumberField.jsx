import { useEffect, useState } from 'react'

/**
 * Shared numeric input for generation forms.
 * Keeps the raw string while typing so values can be decreased freely;
 * emits a finite number on each valid keystroke and clamps to [min, max]
 * on blur (empty/invalid reverts to the last committed value).
 */
export default function NumberField({ value, onChange, min = 1, max = 10000, className = 'input', ...rest }) {
  const [text, setText] = useState(value == null ? '' : String(value))

  useEffect(() => {
    setText(value == null ? '' : String(value))
  }, [value])

  const handleChange = (e) => {
    const raw = e.target.value
    setText(raw)
    if (raw.trim() === '') return
    const n = Number(raw)
    if (Number.isFinite(n)) onChange(n)
  }

  const handleBlur = () => {
    const n = Number(text)
    if (text.trim() === '' || !Number.isFinite(n)) {
      const fallback = value != null ? value : min
      setText(String(fallback))
      onChange(fallback)
      return
    }
    const clamped = Math.min(max, Math.max(min, Math.round(n)))
    setText(String(clamped))
    if (clamped !== n) onChange(clamped)
  }

  return (
    <input
      type="number"
      className={className}
      value={text}
      min={min}
      max={max}
      onChange={handleChange}
      onBlur={handleBlur}
      {...rest}
    />
  )
}
