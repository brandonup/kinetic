// src/lib/prompts/weekly-review.ts

export interface WeeklyReviewContext {
  weekStart: string
  weekEnd: string
  meetingsThisWeek: Array<{
    date: string
    contact_name: string
    company: string
    type: string
    ai_summary: string | null
    pain_points_mentioned: string[]
  }>
  followUpsDue: Array<{
    contact_name: string
    type: string
    due_date: string
    status: string
  }>
  knowledgeAddedThisWeek: Array<{
    title: string
    categories: string[]
  }>
  activePatterns: Array<{
    description: string
    pattern_type: string
    confidence: string
  }>
  practiceMemory: Array<{
    memory_type: string
    content: string
    created_at: string
  }>
  hasEnoughHistoricalData: boolean // true if 5+ prior meetings
  neglectedContacts: Array<{
    name: string
    company: string
    days_since_contact: number
  }>
}

export function weeklyReviewPrompt(ctx: WeeklyReviewContext): string {
  return `Generate a weekly review for an AI consulting practice covering ${ctx.weekStart} to ${ctx.weekEnd}.

## This Week's Meetings (${ctx.meetingsThisWeek.length})
${ctx.meetingsThisWeek.length > 0
  ? ctx.meetingsThisWeek.map(m =>
    `- ${new Date(m.date).toLocaleDateString()} | ${m.contact_name} @ ${m.company} (${m.type})
     Summary: ${m.ai_summary || 'Not processed'}
     Pain points: ${m.pain_points_mentioned?.join(', ') || 'None recorded'}`
  ).join('\n')
  : 'No meetings logged this week.'}

## Follow-Ups Status
${ctx.followUpsDue.length > 0
  ? ctx.followUpsDue.map(f => `- ${f.contact_name}: ${f.type} due ${f.due_date} [${f.status}]`).join('\n')
  : 'No follow-ups due.'}

## Knowledge Captured This Week (${ctx.knowledgeAddedThisWeek.length} items)
${ctx.knowledgeAddedThisWeek.length > 0
  ? ctx.knowledgeAddedThisWeek.map(k => `- "${k.title}" [${k.categories?.join(', ')}]`).join('\n')
  : 'No knowledge items added this week.'}

## Active Patterns Detected
${ctx.activePatterns.length > 0
  ? ctx.activePatterns.map(p => `- [${p.pattern_type}, ${p.confidence}] ${p.description}`).join('\n')
  : 'No patterns detected yet.'}

## Practice Memory (Recent)
${ctx.practiceMemory.length > 0
  ? ctx.practiceMemory.slice(0, 5).map(m => `- [${m.memory_type}] ${m.content}`).join('\n')
  : 'No practice memory entries yet.'}

## Contacts With No Recent Activity
${ctx.neglectedContacts.length > 0
  ? ctx.neglectedContacts.map(c => `- ${c.name} @ ${c.company}: ${c.days_since_contact} days since last contact`).join('\n')
  : 'All active contacts have recent activity.'}

---

Generate the weekly review with these sections. Apply all Intelligence Layer instructions from your system prompt.

REQUIRED SECTIONS (always include):
1. **The State of the Practice** — 1 paragraph compressing where things stand: pipeline, relationships, knowledge, momentum (Synthesis)
2. **This Week at a Glance** — bullet summary of meetings, knowledge captured, follow-ups completed
3. **Follow-Ups to Action** — pending follow-ups that need attention with priority order
4. **This Week's Uncomfortable Question** — one genuinely difficult question about the practice based on the data (Generative Questioning + Intellectual Honesty). Be specific, not generic.

CONDITIONAL SECTIONS (include only when data supports it):
5. **Emerging Patterns** — only if patterns exist: describe them with supporting evidence
6. **Gradual Shifts You Might Not Notice** — only if ${ctx.hasEnoughHistoricalData ? 'YES — 5+ prior meetings of data, look for drift in client priorities, relationship tone, or focus areas (Temporal Intelligence)' : 'NO — insufficient historical data yet'}
7. **What You Might Be Avoiding** — only if neglected contacts or unaddressed follow-ups suggest avoidance behavior (Intellectual Honesty)
8. **Knowledge to Apply** — only if knowledge items were added this week that connect to active client needs

Format as clean markdown.`
}
