'use client'
// src/app/knowledge/AddKnowledgeForm.tsx
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export function AddKnowledgeForm() {
  const router = useRouter()
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const text = value.trim()
    if (!text) return

    setLoading(true)
    setError(null)

    const isUrl = text.startsWith('http')
    const body = isUrl ? { source_url: text } : { raw_content: text }

    try {
      const res = await fetch('/api/knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const { item } = await res.json()
        router.push(`/knowledge/${item.id}`)
      } else {
        const data = await res.json()
        setError(data.error || 'Failed to add item')
      }
    } catch {
      setError('Request failed — check your connection')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-bg-surface border border-border-subtle rounded p-4 space-y-3">
      <h2 className="text-xs font-medium text-content-secondary uppercase tracking-wider">
        Add to Knowledge Base
      </h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder="Paste text, URL, or YouTube link..."
          rows={3}
          disabled={loading}
          className="w-full bg-bg-base border border-border-subtle rounded px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-accent-teal resize-none disabled:opacity-50"
        />
        {error && <p className="text-xs text-status-warning">{error}</p>}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={loading || !value.trim()}
            className="px-4 py-2 bg-accent-teal text-bg-base text-sm font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {loading ? 'Processing…' : 'Add Item'}
          </button>
          <span className="text-xs text-content-muted">URL, YouTube link, or raw text</span>
        </div>
      </form>
    </div>
  )
}
