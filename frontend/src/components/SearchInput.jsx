import { Search } from 'lucide-react'

/**
 * Shared search input with a correctly positioned magnifier icon.
 * Icon is absolutely positioned at the inline-start; the input gets
 * matching inline-start padding so text never overlaps the icon in
 * either LTR or RTL layouts.
 */
export default function SearchInput({ value, onChange, placeholder, className = '', ...rest }) {
  return (
    <div className={`relative ${className}`}>
      <Search
        size={15}
        className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-slate-400"
        aria-hidden="true"
      />
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="input w-full ps-9"
        {...rest}
      />
    </div>
  )
}
