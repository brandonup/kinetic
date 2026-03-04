// src/lib/anthropic.ts
import Anthropic from '@anthropic-ai/sdk'

if (!process.env.ANTHROPIC_API_KEY) throw new Error('Missing ANTHROPIC_API_KEY')

export const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
})

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
  const message = await anthropic.messages.create({
    model,
    max_tokens: maxTokens,
    system: systemPrompt,
    messages: [{ role: 'user', content: userMessage }],
  })

  const block = message.content[0]
  if (block.type !== 'text') throw new Error('Unexpected non-text response from LLM')
  return block.text
}
