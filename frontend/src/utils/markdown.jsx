import React, { useState } from 'react'

function Inline({ text }) {
  // Inline markdown: `code`, **bold**, *italic*, [label](url), $math$
  const parts = []
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]+\]\([^)\s]+\))|(\$[^$\n]+\$)/g
  let last = 0
  let m
  let key = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('`')) {
      parts.push(<code key={key++} className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[0.85em] dark:bg-slate-700/70">{tok.slice(1, -1)}</code>)
    } else if (tok.startsWith('**')) {
      parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('*')) {
      parts.push(<em key={key++}>{tok.slice(1, -1)}</em>)
    } else if (tok.startsWith('[')) {
      const lm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(tok)
      if (lm) {
        const safe = /^https?:\/\//i.test(lm[2]) ? lm[2] : null
        parts.push(safe
          ? <a key={key++} href={safe} target="_blank" rel="noopener noreferrer" className="underline decoration-teal-500 underline-offset-2 hover:text-teal-600">{lm[1]}</a>
          : <span key={key++}>{lm[1]}</span>)
      } else parts.push(tok)
    } else if (tok.startsWith('$')) {
      parts.push(<code key={key++} className="rounded bg-violet-100/70 px-1 py-0.5 font-mono text-[0.9em] text-violet-800 dark:bg-violet-950/50 dark:text-violet-200">{tok.slice(1, -1)}</code>)
    }
    last = m.index + tok.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable */ }
  }
  return (
    <div className="my-2 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
      <div className="flex items-center justify-between bg-slate-100 px-3 py-1 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        <span>{lang || 'code'}</span>
        <button type="button" onClick={copy} className="hover:text-teal-600">
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto bg-slate-900 p-3 text-xs leading-relaxed text-slate-100 dark:bg-slate-950" dir="ltr">
        <code>{code}</code>
      </pre>
    </div>
  )
}

export default function MarkdownText({ text }) {
  const blocks = []
  const lines = String(text || '').split('\n')
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i]
    // Fenced code block
    const fence = /^```(\w*)\s*$/.exec(line)
    if (fence) {
      const buf = []
      i++
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { buf.push(lines[i]); i++ }
      i++ // skip closing fence
      blocks.push(<CodeBlock key={key++} code={buf.join('\n')} lang={fence[1]} />)
      continue
    }
    // Blank line
    if (!line.trim()) { i++; continue }
    // Heading
    const h = /^(#{1,4})\s+(.*)$/.exec(line)
    if (h) {
      const lvl = h[1].length
      const cls = ['text-lg font-bold', 'text-base font-bold', 'text-sm font-bold', 'text-sm font-semibold'][lvl - 1]
      const Tag = `h${Math.min(lvl + 1, 6)}`
      blocks.push(React.createElement(Tag, { key: key++, className: `mt-2 ${cls}` }, <Inline text={h[2]} />))
      i++
      continue
    }
    // Unordered list
    if (/^\s*[-*â€¢]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*[-*â€¢]\s+/.test(lines[i])) {
        items.push(<li key={items.length}><Inline text={lines[i].replace(/^\s*[-*â€¢]\s+/, '')} /></li>)
        i++
      }
      blocks.push(<ul key={key++} className="my-1 list-disc space-y-0.5 ps-5">{items}</ul>)
      continue
    }
    // Ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(<li key={items.length}><Inline text={lines[i].replace(/^\s*\d+[.)]\s+/, '')} /></li>)
        i++
      }
      blocks.push(<ol key={key++} className="my-1 list-decimal space-y-0.5 ps-5">{items}</ol>)
      continue
    }
    // Paragraph â€” merge consecutive plain lines
    const buf = [line]
    i++
    while (i < lines.length && lines[i].trim() &&
           !/^```/.test(lines[i]) && !/^#{1,4}\s/.test(lines[i]) &&
           !/^\s*[-*â€¢]\s+/.test(lines[i]) && !/^\s*\d+[.)]\s+/.test(lines[i])) {
      buf.push(lines[i]); i++
    }
    blocks.push(<p key={key++} className="my-1 leading-relaxed"><Inline text={buf.join(' ')} /></p>)
  }
  return <div className="space-y-0.5">{blocks}</div>
}
