// src/app/layout.tsx
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Kinetic',
  description: 'AI co-pilot for your consulting practice',
}

export const viewport: Viewport = {
  themeColor: '#0a0a0a',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" style={{ colorScheme: 'dark' }}>
      <head>
        <meta name="theme-color" content="#0a0a0a" />
      </head>
      <body className="bg-bg-base text-content-primary min-h-screen">
        {/* Skip link — accessibility guideline */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-accent-teal focus:text-bg-base focus:rounded focus:text-sm focus:font-medium"
        >
          Skip to main content
        </a>

        <div className="flex h-screen overflow-hidden">
          {/* Sidebar */}
          <nav
            aria-label="Main navigation"
            className="w-56 bg-bg-surface border-r border-border-subtle flex-shrink-0 flex flex-col"
          >
            <div className="p-4 border-b border-border-subtle">
              <span className="text-accent-teal font-mono font-bold text-lg tracking-tight">
                KINETIC
              </span>
            </div>
            <div className="flex-1 py-2">
              <NavLink href="/" label="Dashboard" />
              <NavLink href="/contacts" label="Contacts" />
              <NavLink href="/meetings" label="Meetings" />
              <NavLink href="/follow-ups" label="Follow-ups" />
              <NavLink href="/knowledge" label="Knowledge" />
              <NavLink href="/clients" label="Clients" />
            </div>
          </nav>

          {/* Main content */}
          <main id="main-content" className="flex-1 overflow-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}

function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="block px-4 py-2 text-sm text-content-secondary hover:text-content-primary hover:bg-bg-elevated transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-teal focus-visible:ring-inset"
    >
      {label}
    </a>
  )
}
