// src/app/chat/page.tsx
'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  role: 'user' | 'assistant'
  content: string
}

// ─── Markdown Renderer ────────────────────────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[.+?\]\(.+?\))/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold text-content-primary">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={i} className="font-mono text-xs bg-bg-elevated px-1.5 py-0.5 rounded text-accent-teal border border-border-subtle">
          {part.slice(1, -1)}
        </code>
      )
    }
    const linkMatch = part.match(/^\[(.+?)\]\((.+?)\)$/)
    if (linkMatch) {
      return (
        <a key={i} href={linkMatch[2]} target="_blank" rel="noopener noreferrer"
           className="text-accent-teal underline underline-offset-2 hover:opacity-80">
          {linkMatch[1]}
        </a>
      )
    }
    return part
  })
}

function SimpleMarkdown({ text, streaming }: { text: string; streaming?: boolean }) {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Fenced code block
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      elements.push(
        <div key={`code-${i}`} className="my-3">
          {lang && (
            <div className="flex items-center gap-2 bg-bg-elevated border border-border-subtle border-b-0 rounded-t px-3 py-1.5">
              <span className="text-xs font-mono text-content-muted uppercase tracking-widest">{lang}</span>
            </div>
          )}
          <pre className={`bg-bg-elevated border border-border-subtle ${lang ? 'rounded-b' : 'rounded'} px-4 py-3 overflow-x-auto`}>
            <code className="text-xs font-mono text-content-primary leading-relaxed">
              {codeLines.join('\n')}
            </code>
          </pre>
        </div>
      )
      i++
      continue
    }

    // Headers
    if (line.startsWith('### ')) {
      elements.push(
        <h3 key={`h3-${i}`} className="text-xs font-mono font-semibold text-accent-teal uppercase tracking-widest mt-4 mb-1.5">
          {line.slice(4)}
        </h3>
      )
      i++; continue
    }
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={`h2-${i}`} className="text-sm font-semibold text-content-primary mt-4 mb-2 border-b border-border-subtle pb-1">
          {line.slice(3)}
        </h2>
      )
      i++; continue
    }
    if (line.startsWith('# ')) {
      elements.push(
        <h1 key={`h1-${i}`} className="text-base font-semibold text-content-primary mt-4 mb-2">
          {line.slice(2)}
        </h1>
      )
      i++; continue
    }

    // Horizontal rule
    if (line.match(/^[-*]{3,}$/) || line === '---') {
      elements.push(<hr key={`hr-${i}`} className="border-border-subtle my-3" />)
      i++; continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) {
        quoteLines.push(lines[i].slice(2))
        i++
      }
      elements.push(
        <blockquote key={`bq-${i}`} className="border-l-2 border-accent-teal-muted pl-3 my-2 text-content-secondary italic text-sm">
          {quoteLines.map((l, j) => <p key={j}>{renderInline(l)}</p>)}
        </blockquote>
      )
      continue
    }

    // Unordered list
    if (line.match(/^[-*+] /)) {
      const items: string[] = []
      while (i < lines.length && lines[i].match(/^[-*+] /)) {
        items.push(lines[i].replace(/^[-*+] /, ''))
        i++
      }
      elements.push(
        <ul key={`ul-${i}`} className="my-2 space-y-1">
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

    // Numbered list
    if (line.match(/^\d+\. /)) {
      const items: string[] = []
      let num = 1
      while (i < lines.length && lines[i].match(/^\d+\. /)) {
        items.push(lines[i].replace(/^\d+\. /, ''))
        i++
        num++
      }
      elements.push(
        <ol key={`ol-${i}`} className="my-2 space-y-1">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2 text-sm leading-relaxed">
              <span className="text-accent-teal font-mono flex-shrink-0 w-5 text-right mt-0.5">{j + 1}.</span>
              <span className="text-content-primary">{renderInline(item)}</span>
            </li>
          ))}
        </ol>
      )
      void num
      continue
    }

    // Empty line
    if (line.trim() === '') {
      i++; continue
    }

    // Paragraph
    elements.push(
      <p key={`p-${i}`} className="text-sm leading-relaxed text-content-primary my-1.5">
        {renderInline(line)}
      </p>
    )
    i++
  }

  return (
    <div className="prose-kinetic">
      {elements}
      {streaming && (
        <span
          className="inline-block w-2 h-4 bg-accent-teal ml-0.5 align-text-bottom"
          style={{ animation: 'blink 0.8s step-end infinite' }}
        />
      )}
    </div>
  )
}

// ─── Suggested Prompts ────────────────────────────────────────────────────────

const SUGGESTED_PROMPTS = [
  {
    label: 'Prep for a meeting',
    prompt: 'How should I prepare for a discovery call with a new SMB client interested in AI automation?',
    icon: '◈',
  },
  {
    label: 'Decode industry trends',
    prompt: 'What AI trends should I be referencing in my consulting conversations this quarter?',
    icon: '◎',
  },
  {
    label: 'Challenge my thinking',
    prompt: 'What am I likely wrong about when it comes to AI adoption timelines for SMBs?',
    icon: '◻',
  },
]

// ─── Message Bubble ───────────────────────────────────────────────────────────

function MessageBubble({ message, isStreaming }: { message: Message; isStreaming: boolean }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%]">
          <div className="flex items-center justify-end gap-2 mb-1.5">
            <span className="text-xs font-mono text-content-muted tracking-widest uppercase">You</span>
          </div>
          <div className="bg-bg-elevated border border-border-DEFAULT rounded-2xl rounded-tr-sm px-4 py-3">
            <p className="text-sm text-content-primary leading-relaxed whitespace-pre-wrap">{message.content}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-4">
      {/* Timeline bar */}
      <div className="flex-shrink-0 flex flex-col items-center pt-6">
        <div className="w-px flex-1 bg-border-subtle" />
        <div
          className="w-1.5 h-1.5 rounded-full bg-accent-teal flex-shrink-0 my-1"
          style={isStreaming ? { animation: 'pulse 1.2s ease-in-out infinite', boxShadow: '0 0 8px #00b5a3' } : {}}
        />
        <div className="w-px flex-1 bg-border-subtle" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-2">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono text-accent-teal tracking-widest uppercase">Kinetic</span>
          {isStreaming && (
            <span className="text-xs font-mono text-content-muted" style={{ animation: 'fadeInOut 1.5s ease-in-out infinite' }}>
              ··· receiving
            </span>
          )}
        </div>
        <div className="bg-bg-surface border border-border-subtle rounded-xl rounded-tl-sm px-4 py-3">
          <SimpleMarkdown text={message.content} streaming={isStreaming} />
        </div>
      </div>
    </div>
  )
}

// ─── Thinking Indicator ───────────────────────────────────────────────────────

function ThinkingIndicator() {
  return (
    <div className="flex gap-4">
      <div className="flex-shrink-0 flex flex-col items-center pt-6">
        <div className="w-px flex-1 bg-border-subtle" />
        <div
          className="w-1.5 h-1.5 rounded-full bg-accent-teal flex-shrink-0 my-1"
          style={{ animation: 'pulse 1.2s ease-in-out infinite', boxShadow: '0 0 8px #00b5a3' }}
        />
        <div className="w-px flex-1 bg-border-subtle" />
      </div>
      <div className="flex-1 pb-2 pt-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono text-accent-teal tracking-widest uppercase">Kinetic</span>
          <span className="text-xs font-mono text-content-muted">··· thinking</span>
        </div>
        <div className="flex gap-1.5 px-4 py-3">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-content-muted"
              style={{ animation: `bounce 1.2s ease-in-out ${i * 0.15}s infinite` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Empty State ──────────────────────────────────────────────────────────────

function EmptyState({ onPrompt }: { onPrompt: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full py-16 px-4">
      <div className="mb-2">
        <div className="flex items-center gap-2 justify-center">
          <div className="w-8 h-px bg-accent-teal-muted" />
          <span className="text-xs font-mono text-accent-teal tracking-widest uppercase">Intelligence Layer</span>
          <div className="w-8 h-px bg-accent-teal-muted" />
        </div>
      </div>
      <h2 className="text-lg font-semibold text-content-primary mt-3 mb-1 text-center">
        What do you need to know?
      </h2>
      <p className="text-sm text-content-secondary text-center mb-8 max-w-sm">
        Ask about clients, strategy, industry trends, or meeting prep. Kinetic searches your knowledge base and synthesizes an answer.
      </p>
      <div className="grid grid-cols-1 gap-3 w-full max-w-xl">
        {SUGGESTED_PROMPTS.map(sp => (
          <button
            key={sp.label}
            onClick={() => onPrompt(sp.prompt)}
            className="group text-left bg-bg-surface border border-border-subtle rounded-xl px-4 py-3.5 hover:border-accent-teal transition-all duration-200 hover:bg-bg-elevated"
          >
            <div className="flex items-start gap-3">
              <span className="font-mono text-accent-teal-muted group-hover:text-accent-teal transition-colors text-base flex-shrink-0 mt-0.5">
                {sp.icon}
              </span>
              <div>
                <p className="text-xs font-mono text-content-muted uppercase tracking-wider mb-1 group-hover:text-accent-teal transition-colors">
                  {sp.label}
                </p>
                <p className="text-sm text-content-secondary group-hover:text-content-primary transition-colors leading-relaxed">
                  {sp.prompt}
                </p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── Chat Core ────────────────────────────────────────────────────────────────

function ChatCore() {
  const searchParams = useSearchParams()
  const contactId = searchParams.get('contact_id') ?? undefined
  const initialQ = searchParams.get('q') ?? ''

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState(initialQ)
  const [streaming, setStreaming] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [currentResponse, setCurrentResponse] = useState('')

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentResponse, thinking])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`
    }
  }, [input])

  // Auto-submit if ?q= is present on mount
  useEffect(() => {
    if (initialQ && messages.length === 0) {
      void sendMessage(initialQ)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return

    const newHistory: Message[] = [...messages, { role: 'user', content: trimmed }]
    setMessages(newHistory)
    setInput('')
    setThinking(true)
    setStreaming(false)
    setCurrentResponse('')

    abortRef.current = new AbortController()

    try {
      const res = await fetch('/api/knowledge/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortRef.current.signal,
        body: JSON.stringify({
          message: trimmed,
          contact_id: contactId,
          messages: messages, // history before the new user message
        }),
      })

      if (!res.ok || !res.body) throw new Error('Stream failed')

      setThinking(false)
      setStreaming(true)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let full = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') break
            try {
              const parsed = JSON.parse(data) as { text?: string; error?: string }
              if (parsed.text) {
                full += parsed.text
                setCurrentResponse(full)
              }
            } catch {
              // ignore malformed SSE lines
            }
          }
        }
      }

      setMessages([...newHistory, { role: 'assistant', content: full }])
      setCurrentResponse('')
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') return
      console.error(err)
      setMessages([
        ...newHistory,
        { role: 'assistant', content: 'Something went wrong. Please try again.' },
      ])
      setCurrentResponse('')
    } finally {
      setThinking(false)
      setStreaming(false)
    }
  }, [messages, streaming, contactId])

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    void sendMessage(input)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage(input)
    }
  }

  const handlePrompt = (text: string) => {
    setInput(text)
    void sendMessage(text)
  }

  // Build the display message list (inject in-progress response as the last message)
  const displayMessages: Message[] =
    currentResponse
      ? [...messages, { role: 'assistant', content: currentResponse }]
      : messages

  const isActive = streaming || thinking

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <div className="flex-shrink-0 border-b border-border-subtle px-6 py-3.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-accent-teal tracking-widest uppercase">
              Intelligence Layer
            </span>
            <div className="flex items-center gap-1.5">
              <div
                className="w-1.5 h-1.5 rounded-full bg-accent-teal"
                style={isActive
                  ? { animation: 'pulse 1s ease-in-out infinite', boxShadow: '0 0 6px #00b5a3' }
                  : { opacity: 0.6 }}
              />
              <span className="text-xs font-mono text-content-muted">
                {isActive ? 'processing' : 'ready'}
              </span>
            </div>
          </div>
          {contactId && (
            <span className="text-xs font-mono text-content-muted bg-bg-elevated border border-border-subtle rounded px-2 py-0.5">
              client context active
            </span>
          )}
          {messages.length > 0 && (
            <button
              onClick={() => { setMessages([]); setCurrentResponse('') }}
              className="text-xs text-content-muted hover:text-content-secondary transition-colors font-mono"
            >
              clear ×
            </button>
          )}
        </div>
      </div>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {displayMessages.length === 0 && !thinking ? (
          <EmptyState onPrompt={handlePrompt} />
        ) : (
          <div className="max-w-3xl mx-auto space-y-4 py-2">
            {displayMessages.map((msg, i) => (
              <MessageBubble
                key={i}
                message={msg}
                isStreaming={streaming && i === displayMessages.length - 1 && msg.role === 'assistant'}
              />
            ))}
            {thinking && <ThinkingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* ── Input Bar ── */}
      <div className="flex-shrink-0 border-t border-border-subtle px-6 py-4 bg-bg-base">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="flex gap-3 items-end">
            <div className="flex-1 relative bg-bg-surface border border-border-subtle rounded-xl focus-within:border-accent-teal transition-colors">
              <span className="absolute left-3.5 top-3 text-accent-teal font-mono text-sm select-none pointer-events-none">›</span>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about clients, strategy, industry trends..."
                disabled={isActive}
                rows={1}
                className="w-full bg-transparent pl-8 pr-4 py-3 text-sm text-content-primary placeholder-content-muted focus:outline-none resize-none disabled:opacity-50"
                style={{ minHeight: '44px', maxHeight: '160px' }}
              />
            </div>
            <button
              type="submit"
              disabled={!input.trim() || isActive}
              className="flex-shrink-0 h-11 px-5 bg-accent-teal text-bg-base text-sm font-medium rounded-xl hover:opacity-90 disabled:opacity-40 transition-opacity font-mono"
            >
              {isActive ? '···' : 'Send'}
            </button>
          </div>
          <p className="text-xs text-content-muted mt-2 text-center font-mono">
            ↵ to send · shift+↵ for newline
          </p>
        </form>
      </div>

      {/* ── Keyframe animations ── */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        @keyframes fadeInOut {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-5px); }
        }
      `}</style>
    </div>
  )
}

// ─── Page (wrapped in Suspense for useSearchParams) ────────────────────────────

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center h-full">
        <span className="font-mono text-xs text-content-muted tracking-widest">initializing ···</span>
      </div>
    }>
      <ChatCore />
    </Suspense>
  )
}
