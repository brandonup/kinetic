// src/lib/anthropic.ts
import Anthropic from '@anthropic-ai/sdk'

// Lazy singleton — env check deferred to first call so Next.js build doesn't throw at module eval
let _client: Anthropic | null = null
function getClient(): Anthropic {
  if (!_client) {
    if (!process.env.ANTHROPIC_API_KEY) throw new Error('Missing ANTHROPIC_API_KEY')
    _client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })
  }
  return _client
}

/**
 * Make a single-turn LLM call. Always pass the INTELLIGENCE_LAYER_PROMPT as part of systemPrompt.
 * Model: claude-sonnet-4-5-20250929 for all substantive calls.
 * Use 'claude-haiku-4-5-20251001' for lightweight classification/extraction.
 */
export async function callLLM({
  systemPrompt,
  userMessage,
  model = 'claude-sonnet-4-5-20250929',
  maxTokens = 2048,
}: {
  systemPrompt: string
  userMessage: string
  model?: string
  maxTokens?: number
}): Promise<string> {
  const message = await getClient().messages.create({
    model,
    max_tokens: maxTokens,
    system: systemPrompt,
    messages: [{ role: 'user', content: userMessage }],
  })

  const block = message.content[0]
  if (block.type !== 'text') throw new Error('Unexpected non-text response from LLM')
  return block.text
}
