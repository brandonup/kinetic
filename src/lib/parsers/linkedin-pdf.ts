// src/lib/parsers/linkedin-pdf.ts
import pdfParse from './pdf-adapter'
import { callLLM } from '../anthropic'
import { buildSystemPrompt } from '../intelligence-layer'

export interface LinkedInExtract {
  name?: string
  title?: string
  company?: string
  location?: string
  email?: string
  linkedin_url?: string
  summary?: string
  raw_text: string
}

/**
 * Parse a LinkedIn PDF export and extract structured contact data.
 * Falls back to empty fields if extraction fails — never throw on partial data.
 */
export async function parseLinkedInPDF(buffer: Buffer): Promise<LinkedInExtract> {
  let rawText = ''
  try {
    const parsed = await pdfParse(buffer)
    rawText = parsed.text
  } catch {
    throw new Error('Could not read PDF — ensure this is a valid LinkedIn export')
  }

  if (!rawText || rawText.trim().length < 50) {
    throw new Error('PDF appears empty or unreadable')
  }

  // Use LLM to extract structured data from raw LinkedIn text
  const systemPrompt = buildSystemPrompt(`
You extract structured contact information from raw LinkedIn PDF export text.
Return a JSON object with these exact keys (use null for missing fields):
- "name": string | null
- "title": string | null (current job title)
- "company": string | null (current company)
- "location": string | null
- "email": string | null
- "linkedin_url": string | null
- "summary": string | null (their LinkedIn About/summary section, max 500 chars)

Return only valid JSON. No markdown. No explanation.
`.trim())

  const userMessage = `Extract contact info from this LinkedIn export:\n\n${rawText.slice(0, 4000)}`

  try {
    const response = await callLLM({
      systemPrompt,
      userMessage,
      model: 'claude-haiku-4-5-20251001', // lightweight extraction task
      maxTokens: 512,
    })
    const extracted = JSON.parse(response)
    return { ...extracted, raw_text: rawText }
  } catch {
    // If LLM parsing fails, return raw text so user can fill in manually
    return { raw_text: rawText }
  }
}
