// src/lib/prompts/prep-brief.ts

export interface PrepBriefContext {
  contact: {
    name: string
    company: string
    title: string | null
    ai_summary: string
    relationship_status: string
  }
  meeting?: {
    date: string
    type: string
  }
  recentMeetings: Array<{
    date: string
    ai_summary: string | null
    key_insights: string | null
    pain_points_mentioned: string[]
  }>
  clientMemory: Array<{
    memory_type: string
    content: string
    created_at: string
  }>
  relevantKnowledge: Array<{
    content: string
  }>
  previousMeetingCount: number
}

export function prepBriefPrompt(ctx: PrepBriefContext): string {
  const hasPriorMeetings = ctx.previousMeetingCount > 0
  const hasStakeholderData = ctx.clientMemory.some(m => m.memory_type === 'org_dynamic')
  const hasAssumptions = ctx.clientMemory.some(m => m.memory_type === 'assumption')

  return `You are preparing a meeting prep brief for ${ctx.contact.name} at ${ctx.contact.company}.

## Contact Profile
${ctx.contact.ai_summary}
Relationship status: ${ctx.contact.relationship_status}
${ctx.contact.title ? `Title: ${ctx.contact.title}` : ''}

## Client Memory (Goals, Preferences, Constraints)
${ctx.clientMemory.length > 0
  ? ctx.clientMemory.map(m => `- [${m.memory_type}] ${m.content}`).join('\n')
  : 'No prior context captured yet.'}

## Recent Meeting History (last ${ctx.recentMeetings.length} meetings)
${ctx.recentMeetings.length > 0
  ? ctx.recentMeetings.map(m => `
### Meeting — ${new Date(m.date).toLocaleDateString()}
Summary: ${m.ai_summary || 'Not processed yet'}
Key insights: ${m.key_insights || 'None recorded'}
Pain points: ${m.pain_points_mentioned?.join(', ') || 'None recorded'}`).join('\n')
  : 'No prior meetings.'}

## Relevant Knowledge from Knowledge Base
${ctx.relevantKnowledge.length > 0
  ? ctx.relevantKnowledge.map((k, i) => `[${i + 1}] ${k.content}`).join('\n\n')
  : 'No highly relevant knowledge items found.'}

---

Generate a meeting prep brief with these sections. Follow all Intelligence Layer instructions from your system prompt.

REQUIRED SECTIONS (always include):
1. **The Essential Situation** — 2-3 sentence compressed mental model of where things stand with this client (Synthesis)
2. **Background & Context** — key facts about this contact and company
3. **Talking Points** — 3-5 specific, grounded conversation starters based on their goals and pain points
4. **Questions You Haven't Asked** — 2-3 non-obvious questions grounded in their context, goals, and any knowledge gaps (Generative Questioning)

CONDITIONAL SECTIONS (include only when data supports it):
5. **What's Changed Since Last Meeting** — only if ${hasPriorMeetings ? 'YES — compare current memory to most recent meeting context, highlight shifts in priorities or concerns (Temporal Intelligence)' : 'NO — first meeting or insufficient history'}
6. **How Key Stakeholders Might See This** — only if ${hasStakeholderData ? 'YES — org dynamic context exists, model stakeholder perspectives' : 'NO — insufficient stakeholder data'}
7. **Assumptions at Risk** — only if ${hasAssumptions ? 'YES — tracked assumptions exist, flag any that recent context might contradict (Intellectual Honesty)' : 'NO — no tracked assumptions yet'}
8. **Relevant Knowledge to Reference** — only if relevant knowledge was found

Format as clean markdown. Be specific — use names, dates, and referenced content. No generic advice.`
}

export function clientFacingSummaryPrompt(rawNotes: string, meetingContext: string): string {
  return `You are generating a client-facing meeting summary — professional, polished, and appropriate to share directly with the client.

Meeting context: ${meetingContext}

Raw meeting notes:
${rawNotes}

Generate a clean, professional summary with these sections:
1. **Meeting Overview** — 1-2 sentences on purpose and attendees
2. **Key Discussion Points** — what was covered (no internal strategy notes)
3. **Decisions Made** — any decisions reached
4. **Next Steps** — specific action items with owners and target dates where applicable

Tone: Professional and collaborative. Avoid: internal commentary, strategic assessments, personal notes about the client.
Format: Clean markdown. Max 400 words.`
}
