// src/lib/prompts/contact-summary.test.ts
import { describe, it, expect } from 'vitest'
import { buildContactSummaryPrompt } from './contact-summary'

describe('buildContactSummaryPrompt', () => {
  it('includes name and company in the user message', () => {
    const { userMessage } = buildContactSummaryPrompt({
      name: 'Jane Smith',
      company: 'Acme Corp',
      title: 'VP of Engineering',
    })
    expect(userMessage).toContain('Jane Smith')
    expect(userMessage).toContain('Acme Corp')
  })

  it('system prompt includes Intelligence Layer instruction', () => {
    const { systemPrompt } = buildContactSummaryPrompt({ name: 'Test' })
    expect(systemPrompt).toContain('Intelligence Layer')
  })
})
