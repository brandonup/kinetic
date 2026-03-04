// src/app/clients/[id]/page.tsx
import { notFound } from 'next/navigation'
import { PrepBriefPanel } from './PrepBriefPanel'

// ─── Types ────────────────────────────────────────────────────────────────────

interface MemoryItem {
  id: string
  memory_type: string
  content: string
  created_at: string
}

interface FollowUpItem {
  id: string
  type: string
  due_date: string
  message_draft: string | null
}

interface MeetingItem {
  id: string
  date: string
  type: string
  status: string
  ai_summary: string | null
}

interface KnowledgeHit {
  id: string
  title: string
  content: string
}

interface ContactData {
  id: string
  name: string
  company: string
  title: string | null
  ai_summary: string
  relationship_status: string
}

// ─── Memory Section ───────────────────────────────────────────────────────────

function MemorySection({
  title,
  items,
  accent = false,
}: {
  title: string
  items: MemoryItem[]
  accent?: boolean
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className={`text-xs font-mono font-medium uppercase tracking-wider ${accent ? 'text-accent-teal' : 'text-content-secondary'}`}>
          {title}
        </h2>
        <span className="text-xs font-mono text-content-muted">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-content-muted">None captured yet.</p>
      ) : (
        <ul className="space-y-2">
          {items.map(item => (
            <li
              key={item.id}
              className="text-sm text-content-primary border-b border-border-subtle last:border-0 pb-2 last:pb-0 leading-relaxed"
            >
              {item.content}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default async function ClientContextPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
  const res = await fetch(`${baseUrl}/api/clients/${id}/context`, {
    cache: 'no-store',
  })

  if (!res.ok) notFound()

  const {
    contact,
    memory,
    meetings,
    follow_ups,
    relevant_knowledge,
  }: {
    contact: ContactData
    memory: MemoryItem[]
    meetings: MeetingItem[]
    follow_ups: FollowUpItem[]
    relevant_knowledge: KnowledgeHit[]
  } = await res.json()

  const goals = memory.filter(m => m.memory_type === 'goal')
  const constraints = memory.filter(m => m.memory_type === 'constraint')
  const assumptions = memory.filter(m => m.memory_type === 'assumption')
  const other = memory.filter(
    m => !['goal', 'constraint', 'assumption'].includes(m.memory_type)
  )

  const overdueFollowUps = follow_ups.filter(f => new Date(f.due_date) < new Date())

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <a
            href="/clients"
            className="text-xs text-content-secondary hover:text-accent-teal transition-colors"
          >
            ← Clients
          </a>
          <h1 className="text-xl font-semibold text-content-primary mt-1.5">{contact.name}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            {contact.title && (
              <span className="text-sm text-content-secondary">{contact.title}</span>
            )}
            {contact.title && <span className="text-content-muted">·</span>}
            <span className="text-sm text-content-secondary">{contact.company}</span>
            <span
              className={`text-xs border rounded px-2 py-0.5 ml-1 ${
                contact.relationship_status === 'active'
                  ? 'border-accent-teal text-accent-teal'
                  : 'border-status-warning text-status-warning'
              }`}
            >
              {contact.relationship_status}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <a
            href={`/clients/${id}/intake`}
            className="px-3 py-1.5 border border-border-subtle text-content-secondary text-xs rounded hover:border-accent-teal hover:text-content-primary transition-colors"
          >
            Run Intake
          </a>
          <a
            href={`/chat?contact_id=${id}&q=${encodeURIComponent(`Tell me about ${contact.name} at ${contact.company}`)}`}
            className="px-3 py-1.5 border border-border-subtle text-content-secondary text-xs rounded hover:border-accent-teal hover:text-content-primary transition-colors"
          >
            Chat →
          </a>
          <PrepBriefPanel contactId={id} contactName={contact.name} />
        </div>
      </div>

      {/* AI Summary */}
      {contact.ai_summary && (
        <div className="bg-bg-surface border border-border-subtle rounded p-4">
          <h2 className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider mb-2">
            Profile Summary
          </h2>
          <p className="text-sm text-content-primary leading-relaxed">{contact.ai_summary}</p>
        </div>
      )}

      {/* Overdue follow-ups alert */}
      {overdueFollowUps.length > 0 && (
        <div className="border border-status-warning/40 bg-status-warning/5 rounded p-3 flex items-center gap-3">
          <span className="text-status-warning text-xs font-mono uppercase tracking-widest">Overdue</span>
          <p className="text-xs text-content-secondary">
            {overdueFollowUps.length} follow-up{overdueFollowUps.length > 1 ? 's' : ''} past due
          </p>
          <a href="/follow-ups" className="ml-auto text-xs text-accent-teal hover:underline">View →</a>
        </div>
      )}

      {/* Memory grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <MemorySection title="Goals" items={goals} accent />
        <MemorySection title="Constraints" items={constraints} />
        {assumptions.length > 0 && (
          <MemorySection title="Tracked Assumptions" items={assumptions} />
        )}
        {other.length > 0 && (
          <MemorySection title="Context & Notes" items={other} />
        )}
      </div>

      {/* Follow-ups */}
      {follow_ups.length > 0 && (
        <div className="bg-bg-surface border border-border-subtle rounded p-4">
          <h2 className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider mb-3">
            Pending Follow-Ups
          </h2>
          <div className="space-y-0">
            {follow_ups.map(f => (
              <div
                key={f.id}
                className="flex items-start justify-between py-2.5 border-b border-border-subtle last:border-0 gap-3"
              >
                <div className="min-w-0">
                  <span className="text-sm text-content-primary capitalize">
                    {f.type.replace(/_/g, ' ')}
                  </span>
                  {f.message_draft && (
                    <p className="text-xs text-content-secondary mt-0.5 truncate">
                      {f.message_draft}
                    </p>
                  )}
                </div>
                <span
                  className={`text-xs flex-shrink-0 font-mono ${
                    new Date(f.due_date) < new Date()
                      ? 'text-status-warning'
                      : 'text-content-muted'
                  }`}
                >
                  {new Date(f.due_date).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent meetings */}
      <div className="bg-bg-surface border border-border-subtle rounded p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider">
            Recent Meetings
          </h2>
          <a href="/meetings" className="text-xs text-accent-teal hover:underline">
            All meetings →
          </a>
        </div>
        {meetings.length === 0 ? (
          <p className="text-sm text-content-muted">No meetings logged yet.</p>
        ) : (
          <div className="space-y-0">
            {meetings.slice(0, 5).map(m => (
              <a
                key={m.id}
                href={`/meetings/${m.id}`}
                className="block border-b border-border-subtle last:border-0 py-3 last:pb-0 hover:opacity-80 transition-opacity"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-content-secondary font-mono">
                    {new Date(m.date).toLocaleDateString()} · {m.type}
                  </span>
                  <span
                    className={`text-xs font-mono ${
                      m.status === 'completed' ? 'text-accent-teal' : 'text-content-muted'
                    }`}
                  >
                    {m.status}
                  </span>
                </div>
                {m.ai_summary && (
                  <p className="text-sm text-content-primary line-clamp-2 leading-relaxed">
                    {m.ai_summary}
                  </p>
                )}
              </a>
            ))}
          </div>
        )}
      </div>

      {/* Relevant knowledge */}
      {relevant_knowledge.length > 0 && (
        <div className="bg-bg-surface border border-border-subtle rounded p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider">
              Relevant Knowledge
            </h2>
            <a
              href={`/chat?contact_id=${id}&q=${encodeURIComponent(`What's relevant to ${contact.name} at ${contact.company}?`)}`}
              className="text-xs text-accent-teal hover:underline"
            >
              Ask Kinetic →
            </a>
          </div>
          <div className="space-y-2">
            {relevant_knowledge.slice(0, 4).map((k, i) => (
              <a
                key={k.id ?? i}
                href={k.id ? `/knowledge/${k.id}` : '#'}
                className="block text-xs text-content-secondary border-b border-border-subtle last:border-0 py-2 last:pb-0 hover:text-content-primary transition-colors line-clamp-2"
              >
                {k.title ? (
                  <span className="font-medium text-content-primary">{k.title}</span>
                ) : (
                  k.content?.slice(0, 140)
                )}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
