// src/__tests__/knowledge-api.test.ts
import { describe, it, expect } from 'vitest'
import { parseKnowledgeProcessingResponse } from '@/lib/prompts/knowledge-processing'

describe('parseKnowledgeProcessingResponse', () => {
  it('parses valid JSON', () => {
    const json = JSON.stringify({
      title: 'AI Trends 2026',
      ai_summary: 'Summary here',
      key_takeaways: ['Takeaway 1', 'Takeaway 2'],
      categories: ['market_intelligence'],
      relevance_tags: ['AI', 'trends', '2026'],
    })
    const result = parseKnowledgeProcessingResponse(json)
    expect(result.title).toBe('AI Trends 2026')
    expect(result.ai_summary).toBe('Summary here')
    expect(result.key_takeaways).toHaveLength(2)
    expect(result.categories).toContain('market_intelligence')
    expect(result.relevance_tags).toContain('AI')
  })

  it('handles markdown code blocks (json fence)', () => {
    const json =
      '```json\n{"title":"Test","ai_summary":"s","key_takeaways":[],"categories":["other"],"relevance_tags":[]}\n```'
    const result = parseKnowledgeProcessingResponse(json)
    expect(result.title).toBe('Test')
    expect(result.categories).toContain('other')
  })

  it('handles plain code fence (no language)', () => {
    const json =
      '```\n{"title":"Plain","ai_summary":"x","key_takeaways":["k"],"categories":["competitive_intel"],"relevance_tags":[]}\n```'
    const result = parseKnowledgeProcessingResponse(json)
    expect(result.title).toBe('Plain')
    expect(result.key_takeaways).toContain('k')
  })

  it('defaults missing fields gracefully', () => {
    const json = JSON.stringify({ title: 'Only Title' })
    const result = parseKnowledgeProcessingResponse(json)
    expect(result.title).toBe('Only Title')
    expect(result.ai_summary).toBeDefined()
    expect(result.key_takeaways).toEqual([])
    expect(result.categories).toEqual(['other'])
    expect(result.relevance_tags).toEqual([])
  })

  it('trims whitespace around JSON', () => {
    const json = `   \n${JSON.stringify({
      title: 'Trimmed',
      ai_summary: 'trim test',
      key_takeaways: [],
      categories: ['other'],
      relevance_tags: [],
    })}\n   `
    const result = parseKnowledgeProcessingResponse(json)
    expect(result.title).toBe('Trimmed')
  })

  it('handles all valid category values', () => {
    const categories = [
      'market_intelligence',
      'methodology',
      'client_context',
      'competitive_intel',
      'thought_leadership',
      'case_study',
      'other',
    ]
    for (const cat of categories) {
      const json = JSON.stringify({
        title: `Category Test: ${cat}`,
        ai_summary: 'summary',
        key_takeaways: [],
        categories: [cat],
        relevance_tags: [],
      })
      const result = parseKnowledgeProcessingResponse(json)
      expect(result.categories).toContain(cat)
    }
  })
})
