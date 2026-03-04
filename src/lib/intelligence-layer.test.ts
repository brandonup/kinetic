// src/lib/intelligence-layer.test.ts
import { describe, it, expect } from 'vitest'
import { INTELLIGENCE_LAYER_PROMPT, buildSystemPrompt } from './intelligence-layer'

describe('INTELLIGENCE_LAYER_PROMPT', () => {
  it('is a non-empty string', () => {
    expect(typeof INTELLIGENCE_LAYER_PROMPT).toBe('string')
    expect(INTELLIGENCE_LAYER_PROMPT.length).toBeGreaterThan(100)
  })

  it('includes all seven capability names', () => {
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Generative Questioning')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Synthesis')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Perspective Shifting')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Pattern Recognition')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Intellectual Honesty')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Temporal')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Counterfactual')
  })
})

describe('buildSystemPrompt', () => {
  it('combines feature prompt with Intelligence Layer prompt', () => {
    const result = buildSystemPrompt('You are a contact summarizer.')
    expect(result).toContain('You are a contact summarizer.')
    expect(result).toContain('Intelligence Layer')
  })
})
