// src/app/knowledge/[id]/page.tsx
import { supabase } from '@/lib/supabase'
import { notFound } from 'next/navigation'

export default async function KnowledgeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  const { data: item, error } = await supabase
    .from('knowledge_items')
    .select('*')
    .eq('id', id)
    .single()

  if (error || !item) notFound()

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <a
            href="/knowledge"
            className="text-xs text-content-secondary hover:text-accent-teal transition-colors"
          >
            ← Knowledge Base
          </a>
          <h1 className="text-lg font-semibold text-content-primary mt-2">{item.title}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs text-content-muted">{item.source_type}</span>
            <span className="text-xs text-content-muted">
              {new Date(item.created_at).toLocaleDateString()}
            </span>
            {item.source_url && (
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent-teal hover:underline"
              >
                Source →
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Categories and tags */}
      <div className="flex flex-wrap gap-2">
        {item.categories?.map((cat: string) => (
          <span
            key={cat}
            className="text-xs border border-accent-teal text-accent-teal rounded px-2 py-0.5"
          >
            {cat}
          </span>
        ))}
        {item.relevance_tags?.map((tag: string) => (
          <span
            key={tag}
            className="text-xs border border-border-subtle text-content-secondary rounded px-2 py-0.5"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* AI Summary */}
      <div className="bg-bg-surface border border-border-subtle rounded p-4">
        <h2 className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-3">
          AI Summary
        </h2>
        <p className="text-sm text-content-primary whitespace-pre-wrap">{item.ai_summary}</p>
      </div>

      {/* Key Takeaways */}
      {item.key_takeaways?.length > 0 && (
        <div className="bg-bg-surface border border-border-subtle rounded p-4">
          <h2 className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-3">
            Key Takeaways
          </h2>
          <ul className="space-y-2">
            {item.key_takeaways.map((t: string, i: number) => (
              <li key={i} className="flex gap-2 text-sm text-content-primary">
                <span className="text-accent-teal font-mono">{i + 1}.</span>
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Quick actions */}
      <div className="flex gap-3">
        <a
          href={`/chat?q=${encodeURIComponent('Tell me more about: ' + item.title)}`}
          className="px-4 py-2 bg-accent-teal text-bg-base text-sm font-medium rounded hover:opacity-90 transition-opacity"
        >
          Chat about this
        </a>
      </div>
    </div>
  )
}
