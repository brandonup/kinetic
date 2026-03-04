// src/app/review/page.tsx
'use client'

import { useState } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReviewStats {
  meetings: number
  knowledge_items: number
  follow_ups_due: number
  neglected_contacts: number
}

interface ReviewData {
  review: string
  week_start: string
  week_end: string
  stats: ReviewStats
}

// ─── Markdown renderer (matches design system) ────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold text-content-primary">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={i} className="font-mono text-xs bg-bg-elevated px-1 rounded text-accent-teal border border-border-subtle">
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

function ReviewMarkdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith('### ')) {
      elements.push(
        <h3 key={`h3-${i}`} className="text-xs font-mono font-semibold text-accent-teal uppercase tracking-widest mt-6 mb-2">
          {line.slice(4)}
        </h3>
      )
      i++; continue
    }
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={`h2-${i}`} className="text-sm font-semibold text-content-primary mt-6 mb-2.5 pb-2 border-b border-border-subtle">
          {line.slice(3)}
        </h2>
      )
      i++; continue
    }
    if (line.startsWith('# ')) {
      elements.push(
        <h1 key={`h1-${i}`} className="text-base font-semibold text-content-primary mt-5 mb-2">
          {line.slice(2)}
        </h1>
      )
      i++; continue
    }
    if (line === '---' || line.match(/^[-*]{3,}$/)) {
      elements.push(<hr key={`hr-${i}`} className="border-border-subtle my-4" />)
      i++; continue
    }
    if (line.startsWith('> ')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) {
        quoteLines.push(lines[i].slice(2))
        i++
      }
      elements.push(
        <blockquote key={`bq-${i}`} className="border-l-2 border-accent-teal-muted pl-4 my-3 space-y-1">
          {quoteLines.map((l, j) => (
            <p key={j} className="text-sm text-content-secondary italic leading-relaxed">{renderInline(l)}</p>
          ))}
        </blockquote>
      )
      continue
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

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  warn = false,
}: {
  label: string
  value: number
  warn?: boolean
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded p-4 text-center">
      <div className={`text-2xl font-mono font-bold ${warn && value > 0 ? 'text-status-warning' : 'text-accent-teal'}`}>
        {value}
      </div>
      <div className="text-xs text-content-secondary mt-1 leading-tight">{label}</div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WeeklyReviewPage() {
  const [data, setData] = useState<ReviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function generateReview() {
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const res = await fetch('/api/review/weekly', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        const e = await res.json() as { error?: string }
        throw new Error(e.error ?? 'Failed to generate review')
      }
      const result = await res.json() as ReviewData
      setData(result)
    } catch (err: unknown) {
      setError((err as Error)?.message ?? 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }

  // Format week range for display
  function weekRange(start: string, end: string) {
    const s = new Date(start)
    const e = new Date(end)
    return `${s.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${e.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-content-primary">Weekly Review</h1>
          <p className="text-xs text-content-muted mt-0.5">
            Structured practice reflection with Intelligence Layer analysis
          </p>
          {data && (
            <p className="text-xs font-mono text-content-secondary mt-1">
              Week of {weekRange(data.week_start, data.week_end)}
            </p>
          )}
        </div>
        <button
          onClick={generateReview}
          disabled={loading}
          className="flex-shrink-0 px-4 py-2 bg-accent-teal text-bg-base text-sm font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity font-mono"
        >
          {loading ? 'Generating···' : data ? 'Regenerate' : 'Generate Review'}
        </button>
      </div>

      {/* Stats grid */}
      {data?.stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Meetings" value={data.stats.meetings} />
          <StatCard label="Knowledge Added" value={data.stats.knowledge_items} />
          <StatCard label="Follow-Ups Due" value={data.stats.follow_ups_due} warn />
          <StatCard label="Re-engage" value={data.stats.neglected_contacts} warn />
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="bg-bg-surface border border-border-subtle rounded p-10 text-center space-y-3">
          <div className="flex justify-center gap-1.5">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-accent-teal"
                style={{ animation: `bounce 1.2s ease-in-out ${i * 0.15}s infinite` }}
              />
            ))}
          </div>
          <p className="text-sm text-content-secondary">Analyzing your week···</p>
          <p className="text-xs text-content-muted">
            Reviewing meetings, follow-ups, knowledge items, and patterns
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-bg-surface border border-status-danger/40 rounded p-4">
          <p className="text-sm text-status-danger">{error}</p>
          <button onClick={generateReview} className="text-xs text-accent-teal hover:underline mt-2">
            Try again →
          </button>
        </div>
      )}

      {/* Review output */}
      {data?.review && (
        <div className="bg-bg-surface border border-border-subtle rounded p-6">
          <ReviewMarkdown text={data.review} />
        </div>
      )}

      {/* Empty state */}
      {!data && !loading && !error && (
        <div className="bg-bg-surface border border-border-subtle rounded p-10 text-center">
          <div className="flex items-center gap-2 justify-center mb-3">
            <div className="w-12 h-px bg-border-DEFAULT" />
            <span className="text-xs font-mono text-content-muted uppercase tracking-widest">Intelligence Layer</span>
            <div className="w-12 h-px bg-border-DEFAULT" />
          </div>
          <p className="text-sm text-content-muted">
            Click &ldquo;Generate Review&rdquo; to analyze your week
          </p>
          <p className="text-xs text-content-muted mt-2">
            Best run Friday afternoon or Monday morning
          </p>
          <div className="mt-6 grid grid-cols-1 gap-2 max-w-sm mx-auto text-left">
            {[
              'What happened this week across all client interactions',
              'Patterns in pain points and recurring themes',
              'Follow-up status and pipeline health',
              'Neglected contacts that need re-engagement',
              'Knowledge gaps and areas to research',
            ].map((item, i) => (
              <div key={i} className="flex gap-2 text-xs text-content-secondary">
                <span className="text-accent-teal font-mono flex-shrink-0">·</span>
                {item}
              </div>
            ))}
          </div>
        </div>
      )}

      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-5px); }
        }
      `}</style>
    </div>
  )
}
