// src/lib/meeting-processor.test.ts
import { describe, it, expect, vi } from 'vitest'

// Mock dependencies before importing the module under test
vi.mock('./anthropic', () => ({ callLLM: vi.fn() }))
vi.mock('./supabase', () => ({ supabase: {} }))
vi.mock('./openai', () => ({ openaiClient: {} }))

import { parseMeetingProcessingResponse } from './meeting-processor'

describe('parseMeetingProcessingResponse', () => {
  it('parses a valid JSON response from the LLM', () => {
    const json = JSON.stringify({
      summary: 'Great meeting about AI strategy.',
      essential_takeaway: 'They need a clear AI roadmap.',
      action_items: [{ text: 'Send proposal', due_date: '2026-03-07', priority: 'high' }],
      pain_points_mentioned: ['No AI strategy'],
      buying_signals: ['Asked about pricing'],
      key_insights: 'Strong interest, budget unclear.',
      assumptions_stated: ['Assumes AI can replace their data team'],
      gaps_not_addressed: 'Did not discuss timeline or stakeholder buy-in.',
    })
    const result = parseMeetingProcessingResponse(json)
    expect(result.summary).toContain('AI strategy')
    expect(result.action_items).toHaveLength(1)
    expect(result.assumptions_stated).toHaveLength(1)
  })

  it('returns safe defaults on malformed JSON', () => {
    const result = parseMeetingProcessingResponse('not valid json')
    expect(result.summary).toBe('')
    expect(result.action_items).toEqual([])
  })
})
