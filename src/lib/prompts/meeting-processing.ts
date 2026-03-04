// src/lib/prompts/meeting-processing.ts
import { buildSystemPrompt } from '../intelligence-layer'

export function buildMeetingProcessingPrompt(params: {
  contactName: string
  contactCompany?: string | null
  rawNotes: string
  clientGoals?: string | null
}): { systemPrompt: string; userMessage: string } {
  const systemPrompt = buildSystemPrompt(`
You are a consulting practice intelligence system processing meeting notes. Extract structured intelligence from raw meeting notes and return it as valid JSON.

Your output must be a single JSON object with these exact keys:
- "summary": string — 3-5 sentence narrative summary of the meeting
- "essential_takeaway": string — 1 sentence Bottom Line compression (Synthesis capability)
- "action_items": array of { "text": string, "due_date": string|null, "priority": "high"|"medium"|"low" }
- "pain_points_mentioned": string[] — specific pain points or challenges mentioned
- "buying_signals": string[] — signals of interest, urgency, or budget readiness
- "key_insights": string — 1-3 sentences on the most important strategic observations
- "assumptions_stated": string[] — beliefs or assumptions the contact stated or implied (Intellectual Honesty capability)
- "gaps_not_addressed": string — what was NOT discussed relative to their apparent needs (Generative Questioning capability)

Return only valid JSON. No markdown code blocks. No explanation outside the JSON.
`.trim())

  const userMessage = `Process these meeting notes:

Contact: ${params.contactName}${params.contactCompany ? ` at ${params.contactCompany}` : ''}
${params.clientGoals ? `Known goals/context: ${params.clientGoals}` : ''}

Meeting notes:
${params.rawNotes}

Return structured JSON as specified.`

  return { systemPrompt, userMessage }
}
