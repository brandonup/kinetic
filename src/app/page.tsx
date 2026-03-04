// src/app/page.tsx
import { supabase } from '@/lib/supabase'
import Link from 'next/link'

export default async function DashboardPage() {
  const today = new Date().toISOString().split('T')[0]

  const [
    { count: contactCount },
    { data: pendingFollowUps },
    { data: recentMeetings },
    { data: upcomingMeetings },
  ] = await Promise.all([
    supabase.from('contacts').select('*', { count: 'exact', head: true }),
    supabase
      .from('follow_ups')
      .select('*, contacts(name, company)')
      .eq('status', 'pending')
      .lte('due_date', today)
      .order('due_date', { ascending: true })
      .limit(5),
    supabase
      .from('meetings')
      .select('*, contacts(name, company)')
      .eq('status', 'completed')
      .order('date', { ascending: false })
      .limit(5),
    supabase
      .from('meetings')
      .select('*, contacts(name, company)')
      .eq('status', 'upcoming')
      .gte('date', new Date().toISOString())
      .order('date', { ascending: true })
      .limit(3),
  ])

  const overdueCount =
    pendingFollowUps?.filter((f) => f.due_date < today).length ?? 0

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1
          className="text-xl font-semibold text-content-primary"
          style={{ textWrap: 'balance' } as React.CSSProperties}
        >
          Dashboard
        </h1>
        <p className="text-sm text-content-secondary mt-0.5">
          {new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
          })}
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <StatCard label="Contacts" value={contactCount ?? 0} href="/contacts" />
        <StatCard
          label="Due Follow-ups"
          value={pendingFollowUps?.length ?? 0}
          href="/follow-ups"
          alert={overdueCount > 0}
          alertLabel={`${overdueCount} overdue`}
        />
        <StatCard
          label="Upcoming Meetings"
          value={upcomingMeetings?.length ?? 0}
          href="/meetings"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Due & Overdue Follow-ups */}
        <Section
          title="Follow-ups Due"
          count={pendingFollowUps?.length}
          href="/follow-ups"
        >
          {pendingFollowUps?.length === 0 ? (
            <EmptyState text="All caught up." />
          ) : (
            pendingFollowUps?.map((f) => {
              const isOverdue = f.due_date < today
              return (
                <ItemRow
                  key={f.id}
                  primary={
                    (f.contacts as { name: string } | null)?.name ?? 'Unknown'
                  }
                  secondary={`${f.type.replace(/_/g, ' ')} · ${f.due_date}`}
                  tag={isOverdue ? 'overdue' : undefined}
                />
              )
            })
          )}
        </Section>

        {/* Upcoming Meetings */}
        <Section
          title="Upcoming Meetings"
          count={upcomingMeetings?.length}
          href="/meetings"
        >
          {upcomingMeetings?.length === 0 ? (
            <EmptyState text="No upcoming meetings." />
          ) : (
            upcomingMeetings?.map((m) => (
              <Link key={m.id} href={`/meetings/${m.id}`}>
                <ItemRow
                  primary={
                    (m.contacts as { name: string } | null)?.name ?? 'Unknown'
                  }
                  secondary={`${m.type.replace(/_/g, ' ')} · ${new Date(m.date).toLocaleDateString()}`}
                />
              </Link>
            ))
          )}
        </Section>

        {/* Recent Meetings */}
        <Section
          title="Recent Meetings"
          count={recentMeetings?.length}
          href="/meetings"
        >
          {recentMeetings?.length === 0 ? (
            <EmptyState text="No meetings yet." />
          ) : (
            recentMeetings?.map((m) => (
              <Link key={m.id} href={`/meetings/${m.id}`}>
                <ItemRow
                  primary={
                    (m.contacts as { name: string } | null)?.name ?? 'Unknown'
                  }
                  secondary={`${m.type.replace(/_/g, ' ')} · ${new Date(m.date).toLocaleDateString()}`}
                />
              </Link>
            ))
          )}
        </Section>
      </div>
    </div>
  )
}

// ---- Sub-components ----

function StatCard({
  label,
  value,
  href,
  alert,
  alertLabel,
}: {
  label: string
  value: number
  href: string
  alert?: boolean
  alertLabel?: string
}) {
  return (
    <a
      href={href}
      className="bg-bg-surface border border-border-subtle rounded p-4 hover:border-border-DEFAULT transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-teal focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base"
    >
      <div
        className={`text-2xl font-mono font-bold ${alert ? 'text-status-warning' : 'text-accent-teal'}`}
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </div>
      <div className="text-xs text-content-secondary mt-1">{label}</div>
      {alert && alertLabel && (
        <div className="text-xs text-status-warning mt-0.5">{alertLabel}</div>
      )}
    </a>
  )
}

function Section({
  title,
  count,
  href,
  children,
}: {
  title: string
  count?: number | null
  href: string
  children: React.ReactNode
}) {
  return (
    <section className="bg-bg-surface border border-border-subtle rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-mono font-medium text-content-secondary uppercase tracking-wider">
          {title}
        </h2>
        {count !== undefined && count !== null && (
          <a
            href={href}
            className="text-xs text-accent-teal hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-teal rounded"
          >
            View all
          </a>
        )}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  )
}

function ItemRow({
  primary,
  secondary,
  tag,
}: {
  primary: string
  secondary: string
  tag?: string
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border-subtle last:border-0">
      <div className="min-w-0 flex-1">
        <div className="text-sm text-content-primary truncate">{primary}</div>
        <div className="text-xs text-content-secondary font-mono truncate">{secondary}</div>
      </div>
      {tag && (
        <span className="ml-3 flex-shrink-0 text-xs text-status-warning border border-status-warning rounded px-1.5 py-0.5">
          {tag}
        </span>
      )}
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <p className="text-sm text-content-muted py-2">{text}</p>
}
