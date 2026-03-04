// src/lib/parsers/linkedin-pdf.test.ts
import { describe, it, expect, vi } from 'vitest'
import { parseLinkedInPDF } from './linkedin-pdf'

// Mock pdf-parse and anthropic
vi.mock('pdf-parse', () => ({
  default: vi.fn().mockResolvedValue({
    text: 'Jane Smith\nVP Engineering at Acme Corp\nPortland, Oregon\njane@acme.com',
  }),
}))

vi.mock('../anthropic', () => ({
  callLLM: vi.fn().mockResolvedValue(
    JSON.stringify({
      name: 'Jane Smith',
      title: 'VP Engineering',
      company: 'Acme Corp',
      location: 'Portland, Oregon',
      email: 'jane@acme.com',
      linkedin_url: null,
      summary: null,
    })
  ),
}))

describe('parseLinkedInPDF', () => {
  it('extracts name and company from a LinkedIn PDF', async () => {
    const result = await parseLinkedInPDF(Buffer.from('fake pdf content'))
    expect(result.name).toBe('Jane Smith')
    expect(result.company).toBe('Acme Corp')
    expect(result.raw_text).toBeTruthy()
  })
})
