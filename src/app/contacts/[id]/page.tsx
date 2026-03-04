// src/app/contacts/[id]/page.tsx
import { supabase } from '@/lib/supabase'
import { notFound } from 'next/navigation'
import Link from 'next/link'

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function ContactDetailPage({ params }: PageProps) {
  const { id } = await params

  const [{ data: contact }, { data: meetings }, { data: followUps }, { data: memories }] =
    await Promise.all([
      supabase.from('contacts').select('*').eq('id', id).single(),
      supabase
        .from('meetings')
        .select('*')
        .eq('contact_id', id)
        .order('date', { ascending: false }),
      supabase
        .from('follow_ups')
        .select('*')
        .eq('contact_id', id)
        .eq('status', 'pending')
        .order('due_date'),
      supabase
        .from('client_memory')
        .select('*')
        .eq('contact_id', id)
        .eq('is_active', true)
        .order('created_at', { ascending: false })
        .limit(5),
    ])

  if (!contact) notFound()

  const statusColor: Record<string, string> = {
    new: 'text-content-muted border-content-muted',
    warm: 'text-yellow-500 border-yellow-500',
    active: 'text-accent-teal border-accent-teal',
    dormant: 'text-content-muted border-content-muted',
  }

  return (
    <div className="p-6 max-w-4xl">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="mb-4">
        <Link
          href="/contacts"
          className="text-xs text-content-secondary hover:text-content-primary transition-colors"
        >
          ← Contacts
        </Link>
      </nav>

      {/* Contact header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1
              className="text-xl font-semibold text-content-primary"
              style={{ textWrap: 'balance' } as React.CSSProperties}
            >
              {contact.name}
            </h1>
            <span
              className={`text-xs font-mono px-1.5 py-0.5 border rounded ${statusColor[contact.relationship_status] ?? statusColor.new}`}
            >
              {contact.relationship_status}
            </span>
            {contact.icp_fit_score && (
              <span className="text-xs font-mono text-accent-teal">
                ICP {contact.icp_fit_score}/5
              </span>
            )}
          </div>
          <p className="text-sm text-content-secondary mt-1">
            {[contact.title, contact.company, contact.location].filter(Boolean).join(' · ')}
          </p>
          {contact.email && (
            <a
              href={`mailto:${contact.email}`}
              className="text-xs text-accent-teal hover:underline mt-1 inline-block"
            >
              {contact.email}
            </a>
          )}
        </div>
        {contact.linkedin_url && (
          <a
            href={contact.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${contact.name} on LinkedIn`}
            className="text-xs text-content-secondary hover:text-accent-teal transition-colors px-3 py-1.5 border border-border-subtle rounded hover:border-border-DEFAULT"
          >
            LinkedIn ↗
          </a>
        )}
      </div>

      {/* AI Summary */}
      {contact.ai_summary && (
        <div className="bg-bg-surface border border-border-subtle rounded p-4 mb-4">
          <h2 className="text-xs font-mono font-medium text-accent-teal uppercase tracking-wider mb-2">
            AI Summary
          </h2>
          <p className="text-sm text-content-primary leading-relaxed">{contact.ai_summary}</p>
        </div>
      )}

      {/* Tags */}
      {contact.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {contact.tags.map((tag: string) => (
            <span
              key={tag}
              className="text-xs font-mono px-2 py-0.5 bg-bg-surface border border-border-subtle rounded text-content-secondary"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Meetings */}
        <section aria-labelledby="meetings-heading">
          <h2
            id="meetings-heading"
            className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider mb-2"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            Meetings ({meetings?.length ?? 0})
          </h2>
          <div className="space-y-2">
            {meetings?.map((m) => (
              <a
                key={m.id}
                href={`/meetings/${m.id}`}
                className="block p-3 bg-bg-surface border border-border-subtle rounded hover:border-border-DEFAULT text-sm transition-colors group"
              >
                <div className="text-content-primary group-hover:text-accent-teal transition-colors capitalize">
                  {m.type.replace(/_/g, ' ')}
                </div>
                <div className="text-xs text-content-secondary mt-0.5 font-mono">
                  {new Date(m.date).toLocaleDateString()} · {m.status}
                </div>
                {m.ai_summary && (
                  <div className="text-xs text-content-muted mt-1 line-clamp-2">
                    {m.ai_summary}
                  </div>
                )}
              </a>
            ))}
            {!meetings?.length && (
              <p className="text-sm text-content-muted py-2">No meetings yet</p>
            )}
          </div>
        </section>

        {/* Right column */}
        <div className="space-y-4">
          {/* Pending Follow-ups */}
          <section aria-labelledby="followups-heading">
            <h2
              id="followups-heading"
              className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider mb-2"
            >
              Pending Follow-ups ({followUps?.length ?? 0})
            </h2>
            <div className="space-y-2">
              {followUps?.map((f) => {
                const isOverdue = f.due_date < new Date().toISOString().split('T')[0]
                return (
                  <div
                    key={f.id}
                    className="p-3 bg-bg-surface border border-border-subtle rounded text-sm"
                  >
                    <div className="text-content-primary capitalize">
                      {f.type.replace(/_/g, ' ')}
                    </div>
                    <div className={`text-xs mt-0.5 font-mono ${isOverdue ? 'text-status-warning' : 'text-content-secondary'}`}>
                      {isOverdue ? 'overdue · ' : 'due · '}
                      {new Date(f.due_date).toLocaleDateString()}
                    </div>
                  </div>
                )
              })}
              {!followUps?.length && (
                <p className="text-sm text-content-muted py-2">No pending follow-ups</p>
              )}
            </div>
          </section>

          {/* Client Memory (assumptions/goals) */}
          {memories && memories.length > 0 && (
            <section aria-labelledby="memory-heading">
              <h2
                id="memory-heading"
                className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider mb-2"
              >
                Memory ({memories.length})
              </h2>
              <div className="space-y-2">
                {memories.map((m) => (
                  <div
                    key={m.id}
                    className="p-3 bg-bg-surface border border-border-subtle rounded text-sm"
                  >
                    <div className="text-xs font-mono text-accent-teal-muted mb-1 capitalize">
                      {m.memory_type}
                    </div>
                    <div className="text-content-secondary text-xs leading-relaxed">
                      {m.content}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      {/* Notes */}
      {contact.notes && (
        <div className="mt-4 p-4 bg-bg-surface border border-border-subtle rounded">
          <h2 className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider mb-2">
            Notes
          </h2>
          <p className="text-sm text-content-primary leading-relaxed whitespace-pre-wrap">
            {contact.notes}
          </p>
        </div>
      )}
    </div>
  )
}
