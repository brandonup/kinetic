// src/lib/prompts/contact-summary.ts
import { buildSystemPrompt } from '../intelligence-layer'

interface ContactInput {
  name: string
  company?: string | null
  title?: string | null
  location?: string | null
  source?: string | null
  notes?: string | null
  linkedin_text?: string | null
}

export function buildContactSummaryPrompt(contact: ContactInput): {
  systemPrompt: string
  userMessage: string
} {
  const systemPrompt = buildSystemPrompt(`
You are a consulting practice intelligence system. Your job is to generate a concise, useful AI summary of a contact for use in meeting prep, relationship management, and identifying consulting opportunities.

The summary should be 2-4 sentences covering: who this person is, their professional context, why they're relevant to an AI consulting practice, and any signals about their needs or fit. Be specific — use the data provided. Do not speculate beyond what's given.
`.trim())

  const userMessage = `Generate a contact summary for:

Name: ${contact.name}
${contact.title ? `Title: ${contact.title}` : ''}
${contact.company ? `Company: ${contact.company}` : ''}
${contact.location ? `Location: ${contact.location}` : ''}
${contact.source ? `How we met: ${contact.source}` : ''}
${contact.notes ? `Notes: ${contact.notes}` : ''}
${contact.linkedin_text ? `LinkedIn context:\n${contact.linkedin_text}` : ''}

Write a 2-4 sentence summary. Be specific and grounded in what's provided. No filler.`

  return { systemPrompt, userMessage }
}
