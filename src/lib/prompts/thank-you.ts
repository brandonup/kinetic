// src/lib/prompts/thank-you.ts
import { buildSystemPrompt } from '../intelligence-layer'

export function buildThankYouPrompt(params: {
  contactName: string
  meetingSummary: string
  actionItems: Array<{ text: string }>
  meetingType: string
}): { systemPrompt: string; userMessage: string } {
  const systemPrompt = buildSystemPrompt(`
You are drafting a brief thank-you message for a consultant to send after a meeting. The message should:
- Be warm but professional
- Reference 1-2 specific things discussed (not generic)
- Mention next steps if action items exist
- Be 3-5 sentences maximum — consultants are busy, so is the recipient
- Sound like it was written by a human, not a corporate template

Return only the message body. No subject line. No "Here is your email:" preamble.
`.trim())

  const userMessage = `Draft a thank-you message after a ${params.meetingType} with ${params.contactName}.

Meeting summary: ${params.meetingSummary}

${params.actionItems.length > 0 ? `Action items agreed to:\n${params.actionItems.map(a => `- ${a.text}`).join('\n')}` : 'No specific action items.'}

Write the thank-you message.`

  return { systemPrompt, userMessage }
}
