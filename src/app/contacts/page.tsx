// src/app/contacts/page.tsx
import { supabase } from '@/lib/supabase'
import type { Contact } from '@/types'
import Link from 'next/link'

interface PageProps {
  searchParams: Promise<{ search?: string }>
}

export default async function ContactsPage({ searchParams }: PageProps) {
  const { search } = await searchParams

  let contacts: Contact[] = []
  if (search) {
    const { data } = await supabase
      .from('contacts')
      .select('*')
      .or(`name.ilike.%${search}%,company.ilike.%${search}%`)
      .order('updated_at', { ascending: false })
    contacts = data ?? []
  } else {
    const { data } = await supabase
      .from('contacts')
      .select('*')
      .order('updated_at', { ascending: false })
    contacts = data ?? []
  }

  const statusConfig: Record<string, { label: string; color: string }> = {
    new:     { label: 'new',     color: 'text-content-muted' },
    warm:    { label: 'warm',    color: 'text-yellow-500' },
    active:  { label: 'active',  color: 'text-accent-teal' },
    dormant: { label: 'dormant', color: 'text-content-muted' },
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1
            className="text-xl font-semibold text-content-primary"
            style={{ textWrap: 'balance' } as React.CSSProperties}
          >
            Contacts
          </h1>
          <p className="text-sm text-content-secondary mt-0.5 font-mono"
             style={{ fontVariantNumeric: 'tabular-nums' }}>
            {contacts.length} total
          </p>
        </div>
        <a
          href="/contacts/new"
          className="px-4 py-2 bg-accent-teal text-bg-base text-sm font-medium rounded hover:bg-accent-teal-hover transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-teal focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base"
        >
          + Add Contact
        </a>
      </div>

      {/* Search bar */}
      <form method="GET" role="search" className="mb-4">
        <label htmlFor="contact-search" className="sr-only">
          Search contacts
        </label>
        <input
          id="contact-search"
          name="search"
          type="search"
          defaultValue={search}
          placeholder="Search by name, company…"
          autoComplete="off"
          spellCheck={false}
          className="w-full bg-bg-surface border border-border-subtle rounded px-4 py-2 text-sm text-content-primary placeholder-content-muted focus:border-accent-teal focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-teal"
        />
      </form>

      {/* Contact list */}
      <div className="space-y-1" role="list" aria-label="Contact list">
        {contacts.length === 0 ? (
          <div className="text-center py-12 text-content-secondary text-sm">
            {search
              ? `No contacts matching "${search}"`
              : 'No contacts yet. Add your first contact.'}
          </div>
        ) : (
          contacts.map((contact) => {
            const status = statusConfig[contact.relationship_status] ?? statusConfig.new
            return (
              <Link
                key={contact.id}
                href={`/contacts/${contact.id}`}
                role="listitem"
                className="flex items-center justify-between p-3 bg-bg-surface hover:bg-bg-elevated rounded border border-border-subtle hover:border-border-DEFAULT transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-content-primary group-hover:text-accent-teal transition-colors truncate">
                      {contact.name}
                    </span>
                    <span className={`text-xs font-mono flex-shrink-0 ${status.color}`}>
                      {status.label}
                    </span>
                    {contact.icp_fit_score && (
                      <span className="text-xs font-mono text-accent-teal-muted flex-shrink-0">
                        icp:{contact.icp_fit_score}/5
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-content-secondary mt-0.5 truncate">
                    {[contact.title, contact.company].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <div
                  className="text-xs text-content-muted flex-shrink-0 ml-4 font-mono"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {new Date(contact.updated_at).toLocaleDateString()}
                </div>
              </Link>
            )
          })
        )}
      </div>
    </div>
  )
}
