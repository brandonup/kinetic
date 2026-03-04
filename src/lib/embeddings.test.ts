// src/lib/embeddings.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createEmbedding } from './embeddings'

// Mock the OpenAI module
vi.mock('./openai', () => ({
  openaiClient: {
    embeddings: {
      create: vi.fn().mockResolvedValue({
        data: [{ embedding: new Array(1536).fill(0.1) }],
      }),
    },
  },
}))

describe('createEmbedding', () => {
  it('returns a vector of 1536 dimensions', async () => {
    const result = await createEmbedding('test text')
    expect(result).toHaveLength(1536)
    expect(typeof result[0]).toBe('number')
  })

  it('throws on empty input', async () => {
    await expect(createEmbedding('')).rejects.toThrow('Cannot embed empty text')
  })
})
