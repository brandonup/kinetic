// src/app/clients/page.tsx
import { supabase } from '@/lib/supabase'

const STATUS_STYLES: Record<string, string> = {
  active: 'border-accent-teal text-accent-teal',
  warm: 'border-status-warning text-status-warning',
  cold: 'border-border-subtle text-content-muted',
  prospect: 'border-border-DEFAULT text-content-secondary',
}

export default async function ClientsPage() {
  const { data: contacts } = await supabase
    .from('contacts')
    .select('id, name, company, title, relationship_status, updated_at')
    .in('relationship_status', ['warm', 'active'])
    .order('updated_at', { ascending: false })

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-content-primary">Client Contexts</h1>
          <p className="text-xs text-content-muted mt-0.5">
            Active and warm relationships with captured intelligence
          </p>
        </div>
        <span className="text-xs font-mono text-content-secondary">
          {contacts?.length || 0} active
        </span>
      </div>

      {/* List */}
      <div className="space-y-2">
        {!contacts || contacts.length === 0 ? (
          <div className="bg-bg-surface border border-border-subtle rounded p-8 text-center">
            <p className="text-sm text-content-muted">
              No warm or active contacts yet.
            </p>
            <p className="text-xs text-content-muted mt-1">
              Add contacts in{' '}
              <a href="/contacts" className="text-accent-teal hover:underline">
                Contacts
              </a>{' '}
              and update their relationship status.
            </p>
          </div>
        ) : (
          contacts.map(c => (
            <a
              key={c.id}
              href={`/clients/${c.id}`}
              className="flex items-center justify-between bg-bg-surface border border-border-subtle rounded p-4 hover:border-accent-teal transition-colors group"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-content-primary group-hover:text-accent-teal transition-colors truncate">
                  {c.name}
                </p>
                <p className="text-xs text-content-secondary truncate">
                  {c.title ? `${c.title} · ` : ''}{c.company}
                </p>
              </div>
              <div className="flex-shrink-0 text-right ml-4">
                <span
                  className={`inline-block text-xs border rounded px-2 py-0.5 ${
                    STATUS_STYLES[c.relationship_status] ?? STATUS_STYLES.cold
                  }`}
                >
                  {c.relationship_status}
                </span>
                <p className="text-xs text-content-muted mt-1">
                  {new Date(c.updated_at).toLocaleDateString()}
                </p>
              </div>
            </a>
          ))
        )}
      </div>
    </div>
  )
}
