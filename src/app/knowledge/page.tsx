// src/app/knowledge/page.tsx
import { supabase } from '@/lib/supabase'
import { AddKnowledgeForm } from './AddKnowledgeForm'

interface KnowledgeListItem {
  id: string
  title: string
  source_type: string
  categories: string[]
  relevance_tags: string[]
  ai_summary: string
  created_at: string
}

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>
}) {
  const { q } = await searchParams

  let items: KnowledgeListItem[] = []

  if (q) {
    // Semantic search via the API (creates embedding + calls match_documents)
    try {
      const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
      const res = await fetch(
        `${baseUrl}/api/knowledge?q=${encodeURIComponent(q)}&limit=20`,
        { cache: 'no-store' }
      )
      const data = await res.json()
      items = data.items || []
    } catch {
      items = []
    }
  } else {
    const { data } = await supabase
      .from('knowledge_items')
      .select('id, title, source_type, categories, relevance_tags, ai_summary, created_at')
      .order('created_at', { ascending: false })
      .limit(30)
    items = data || []
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-content-primary">Knowledge Base</h1>
        <span className="text-xs text-content-secondary">{items.length} items</span>
      </div>

      {/* Search */}
      <form method="GET" className="flex gap-2">
        <input
          type="text"
          name="q"
          defaultValue={q}
          placeholder="Search knowledge base..."
          className="flex-1 bg-bg-surface border border-border-subtle rounded px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-accent-teal"
        />
        <button
          type="submit"
          className="px-4 py-2 bg-accent-teal text-bg-base text-sm font-medium rounded hover:opacity-90 transition-opacity"
        >
          Search
        </button>
        {q && (
          <a
            href="/knowledge"
            className="px-4 py-2 border border-border-subtle rounded text-sm text-content-secondary hover:text-content-primary transition-colors"
          >
            Clear
          </a>
        )}
      </form>

      {/* Add new item form */}
      <AddKnowledgeForm />

      {/* Items list */}
      <div className="space-y-3">
        {items.length === 0 ? (
          <p className="text-sm text-content-muted py-4 text-center">
            {q ? `No results for "${q}"` : 'No knowledge items yet. Add your first item above.'}
          </p>
        ) : (
          items.map(item => (
            <a
              key={item.id}
              href={`/knowledge/${item.id}`}
              className="block bg-bg-surface border border-border-subtle rounded p-4 hover:border-accent-teal transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-content-primary truncate">{item.title}</p>
                  <p className="text-xs text-content-secondary mt-1 line-clamp-2">{item.ai_summary}</p>
                </div>
                <div className="flex-shrink-0 text-right">
                  <span className="text-xs text-content-muted">
                    {new Date(item.created_at).toLocaleDateString()}
                  </span>
                  <div className="flex flex-wrap gap-1 mt-1 justify-end">
                    {item.categories?.slice(0, 2).map((cat: string) => (
                      <span
                        key={cat}
                        className="text-xs border border-accent-teal text-accent-teal rounded px-1.5 py-0.5"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </a>
          ))
        )}
      </div>
    </div>
  )
}
