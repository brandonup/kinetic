// src/lib/embeddings.ts
import { openaiClient } from './openai'

const EMBEDDING_MODEL = 'text-embedding-3-small'
const EMBEDDING_DIMENSIONS = 1536

/**
 * Generate a 1536-dimension embedding for the given text.
 * Used for: contacts, meetings, knowledge_items, client_memory, practice_memory, quick_captures.
 */
export async function createEmbedding(text: string): Promise<number[]> {
  if (!text || text.trim().length === 0) {
    throw new Error('Cannot embed empty text')
  }

  // Truncate to avoid token limit (8191 tokens for text-embedding-3-small)
  // ~4 chars per token, so 32000 chars is a safe ceiling
  const truncated = text.slice(0, 32000)

  const response = await openaiClient.embeddings.create({
    model: EMBEDDING_MODEL,
    input: truncated,
    dimensions: EMBEDDING_DIMENSIONS,
  })

  return response.data[0].embedding
}

/**
 * Formats text from a contact for embedding.
 * Combines the most semantically rich fields.
 */
export function contactEmbeddingText(contact: {
  name: string
  company?: string | null
  title?: string | null
  ai_summary?: string
  notes?: string
  tags?: string[]
}): string {
  return [
    contact.name,
    contact.title,
    contact.company,
    contact.ai_summary,
    contact.notes,
    contact.tags?.join(', '),
  ]
    .filter(Boolean)
    .join('\n')
}

/**
 * Formats text from a meeting for embedding.
 */
export function meetingEmbeddingText(meeting: {
  raw_notes?: string | null
  ai_summary?: string | null
  pain_points_mentioned?: string[]
  key_insights?: string | null
}): string {
  return [
    meeting.ai_summary,
    meeting.raw_notes,
    meeting.key_insights,
    meeting.pain_points_mentioned?.join(', '),
  ]
    .filter(Boolean)
    .join('\n')
}
