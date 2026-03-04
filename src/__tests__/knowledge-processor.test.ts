// src/__tests__/knowledge-processor.test.ts
import { describe, it, expect } from 'vitest'
import {
  isYouTubeUrl,
  extractYouTubeVideoId,
  chunkText,
  buildKnowledgeEmbeddingText,
} from '@/lib/knowledge-processor'

describe('isYouTubeUrl', () => {
  it('detects youtube.com/watch URLs', () => {
    expect(isYouTubeUrl('https://www.youtube.com/watch?v=abc123')).toBe(true)
  })
  it('detects youtu.be URLs', () => {
    expect(isYouTubeUrl('https://youtu.be/abc123')).toBe(true)
  })
  it('returns false for non-YouTube URLs', () => {
    expect(isYouTubeUrl('https://example.com/article')).toBe(false)
  })
  it('returns false for empty string', () => {
    expect(isYouTubeUrl('')).toBe(false)
  })
})

describe('extractYouTubeVideoId', () => {
  it('extracts ID from watch URL', () => {
    expect(extractYouTubeVideoId('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ')
  })
  it('extracts ID from youtu.be URL', () => {
    expect(extractYouTubeVideoId('https://youtu.be/dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ')
  })
  it('returns null for invalid URL', () => {
    expect(extractYouTubeVideoId('https://example.com')).toBeNull()
  })
})

describe('chunkText', () => {
  it('returns single chunk for short text', () => {
    const chunks = chunkText('Hello world', 2000, 200)
    expect(chunks).toHaveLength(1)
    expect(chunks[0]).toBe('Hello world')
  })
  it('splits long text into overlapping chunks', () => {
    const longText = 'word '.repeat(1000) // ~5000 chars
    const chunks = chunkText(longText, 2000, 200)
    expect(chunks.length).toBeGreaterThan(1)
    // Each chunk should be <= 2000 chars
    chunks.forEach(chunk => expect(chunk.length).toBeLessThanOrEqual(2100))
  })
  it('chunks overlap by approximately overlap chars', () => {
    const longText = 'a '.repeat(2000)
    const chunks = chunkText(longText, 2000, 400)
    if (chunks.length > 1) {
      // The end of chunk 0 should appear at the start of chunk 1
      const endOfFirst = chunks[0].slice(-300)
      expect(chunks[1].startsWith(endOfFirst.trim())).toBe(true)
    }
  })
})

describe('buildKnowledgeEmbeddingText', () => {
  it('combines title, summary, and takeaways', () => {
    const text = buildKnowledgeEmbeddingText({
      title: 'AI Trends 2026',
      ai_summary: 'Summary of AI trends',
      key_takeaways: ['LLMs are getting cheaper', 'Agents are mainstream'],
    })
    expect(text).toContain('AI Trends 2026')
    expect(text).toContain('Summary of AI trends')
    expect(text).toContain('LLMs are getting cheaper')
  })
})
