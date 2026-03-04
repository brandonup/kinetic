// src/app/clients/[id]/PrepBriefPanel.tsx
'use client'

import { useState } from 'react'

// ─── Lightweight markdown renderer ───────────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold text-content-primary">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={i} className="font-mono text-xs bg-bg-elevated px-1 rounded text-accent-teal">
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

function BriefMarkdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith('### ')) {
      elements.push(
        <h3 key={`h3-${i}`} className="text-xs font-mono font-semibold text-accent-teal uppercase tracking-widest mt-5 mb-2">
          {line.slice(4)}
        </h3>
      )
      i++; continue
    }
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={`h2-${i}`} className="text-sm font-semibold text-content-primary mt-5 mb-2 border-b border-border-subtle pb-1.5">
          {line.slice(3)}
        </h2>
      )
      i++; continue
    }
    if (line.startsWith('# ')) {
      elements.push(
        <h1 key={`h1-${i}`} className="text-base font-semibold text-content-primary mt-4 mb-2">
          {line.slice(2)}
        </h1>
      )
      i++; continue
    }
    if (line === '---' || line.match(/^[-*]{3,}$/)) {
      elements.push(<hr key={`hr-${i}`} className="border-border-subtle my-3" />)
      i++; continue
    }
    if (line.match(/^[-*+] /)) {
      const items: string[] = []
      while (i < lines.length && lines[i].match(/^[-*+] /)) {
        items.push(lines[i].replace(/^[-*+] /, ''))
        i++
      }
      elements.push(
        <ul key={`ul-${i}`} className="my-2 space-y-1.5">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2 text-sm leading-relaxed">
              <span className="text-accent-teal font-mono flex-shrink-0 mt-0.5">·</span>
              <span className="text-content-primary">{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }
    if (line.match(/^\d+\. /)) {
      const items: string[] = []
      while (i < lines.length && lines[i].match(/^\d+\. /)) {
        items.push(lines[i].replace(/^\d+\. /, ''))
        i++
      }
      elements.push(
        <ol key={`ol-${i}`} className="my-2 space-y-1.5">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2 text-sm leading-relaxed">
              <span className="text-accent-teal font-mono flex-shrink-0 w-5 text-right mt-0.5">{j + 1}.</span>
              <span className="text-content-primary">{renderInline(item)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }
    if (line.trim() === '') { i++; continue }

    elements.push(
      <p key={`p-${i}`} className="text-sm leading-relaxed text-content-primary my-1.5">
        {renderInline(line)}
      </p>
    )
    i++
  }

  return <div>{elements}</div>
}

// ─── Component ────────────────────────────────────────────────────────────────

interface PrepBriefPanelProps {
  contactId: string
  contactName: string
}

export function PrepBriefPanel({ contactId, contactName }: PrepBriefPanelProps) {
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [brief, setBrief] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  async function generate() {
    setState('loading')
    setOpen(true)
    try {
      const res = await fetch(`/api/prep/${contactId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error('Generation failed')
      const data = await res.json() as { brief: { content: string; generated_at: string } }
      setBrief(data.brief.content)
      setGeneratedAt(data.brief.generated_at)
      setState('done')
    } catch {
      setState('error')
    }
  }

  return (
    <>
      <button
        onClick={state === 'idle' || state === 'error' ? generate : undefined}
        disabled={state === 'loading'}
        className="px-3 py-1.5 bg-accent-teal text-bg-base text-xs font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
      >
        {state === 'loading' ? 'Generating···' : state === 'done' ? 'Regenerate Brief' : 'Generate Prep Brief'}
      </button>

      {/* Inline brief panel */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setOpen(false)}
          />
          {/* Panel */}
          <div className="relative z-10 w-full max-w-2xl h-full bg-bg-surface border-l border-border-subtle flex flex-col overflow-hidden">
            {/* Panel header */}
            <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-border-subtle">
              <div>
                <span className="text-xs font-mono text-accent-teal tracking-widest uppercase">Prep Brief</span>
                <h3 className="text-sm font-semibold text-content-primary mt-0.5">{contactName}</h3>
                {generatedAt && (
                  <p className="text-xs text-content-muted">
                    Generated {new Date(generatedAt).toLocaleString()}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {state === 'done' && (
                  <button
                    onClick={generate}
                    className="text-xs text-content-secondary hover:text-content-primary font-mono transition-colors"
                  >
                    regenerate
                  </button>
                )}
                <button
                  onClick={() => setOpen(false)}
                  className="text-content-muted hover:text-content-primary transition-colors text-lg leading-none"
                >
                  ×
                </button>
              </div>
            </div>

            {/* Panel body */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {state === 'loading' && (
                <div className="flex flex-col items-center justify-center h-48 gap-3">
                  <div className="flex gap-1.5">
                    {[0, 1, 2].map(i => (
                      <div
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-accent-teal"
                        style={{ animation: `bounce 1.2s ease-in-out ${i * 0.15}s infinite` }}
                      />
                    ))}
                  </div>
                  <p className="text-xs font-mono text-content-muted">Synthesizing intelligence···</p>
                </div>
              )}
              {state === 'error' && (
                <div className="text-sm text-status-danger py-4 text-center">
                  Generation failed. Check your API connection and try again.
                </div>
              )}
              {state === 'done' && brief && (
                <BriefMarkdown text={brief} />
              )}
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-5px); }
        }
      `}</style>
    </>
  )
}
