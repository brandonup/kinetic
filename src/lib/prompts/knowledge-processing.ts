// src/lib/prompts/knowledge-processing.ts

export function knowledgeProcessingPrompt(content: string, sourceType: string): string {
  return `You are a knowledge management assistant for an AI consulting practice. Analyze the following ${sourceType} content and extract structured information.

Content to analyze:
${content.slice(0, 8000)}${content.length > 8000 ? '\n\n[Content truncated for analysis — full text stored separately]' : ''}

Return ONLY valid JSON in this exact format:
{
  "title": "string — concise descriptive title (max 80 chars)",
  "ai_summary": "string — 2-4 paragraph synthesis of the key ideas, written as if briefing a consultant",
  "key_takeaways": ["string", "string", "string"] — 3-7 specific, actionable takeaways,
  "categories": ["string"] — 1-3 from: [market_intelligence, technical_tools, sales_strategy, case_study, industry_trend, competitor_info, methodology, client_pain_points, pricing_packaging, other],
  "relevance_tags": ["string"] — 3-8 specific tags for semantic search (company names, technologies, concepts, industries)
}

Do not wrap in markdown code blocks. Return raw JSON only.`
}

export interface ParsedKnowledgeItem {
  title: string
  ai_summary: string
  key_takeaways: string[]
  categories: string[]
  relevance_tags: string[]
}

export function parseKnowledgeProcessingResponse(json: string): ParsedKnowledgeItem {
  const clean = json.trim().replace(/^```json\n?/, '').replace(/\n?```$/, '')
  const parsed = JSON.parse(clean)
  return {
    title: String(parsed.title || 'Untitled'),
    ai_summary: String(parsed.ai_summary || ''),
    key_takeaways: Array.isArray(parsed.key_takeaways) ? parsed.key_takeaways.map(String) : [],
    categories: Array.isArray(parsed.categories) ? parsed.categories.map(String) : ['other'],
    relevance_tags: Array.isArray(parsed.relevance_tags) ? parsed.relevance_tags.map(String) : [],
  }
}
