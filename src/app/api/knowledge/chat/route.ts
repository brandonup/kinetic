// src/app/api/knowledge/chat/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest } from 'next/server'
import Anthropic from '@anthropic-ai/sdk'
import { supabase } from '@/lib/supabase'
import { createEmbedding } from '@/lib/embeddings'
import { buildSystemPrompt } from '@/lib/intelligence-layer'

export async function POST(req: NextRequest) {
  const { message, contact_id, messages: history = [] } = await req.json()

  if (!message?.trim()) {
    return new Response(JSON.stringify({ error: 'message required' }), { status: 400 })
  }

  // Lazy client — only instantiated at request time, never at build time
  const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! })

  // Step 1: Semantic search across knowledge base
  const queryEmbedding = await createEmbedding(message)
  const { data: knowledgeResults } = await supabase.rpc('match_documents', {
    query_embedding: queryEmbedding,
    match_threshold: 0.4,
    match_count: 8,
    filter_source: 'knowledge_items',
  })

  // Step 2: If scoped to a client, also search meetings and client memory
  let clientContext = ''
  if (contact_id) {
    const [{ data: contact }, { data: memories }, { data: meetings }] = await Promise.all([
      supabase.from('contacts').select('name, company, ai_summary').eq('id', contact_id).single(),
      supabase.from('client_memory').select('memory_type, content').eq('contact_id', contact_id).eq('is_active', true).limit(10),
      supabase.from('meetings').select('date, ai_summary, key_insights').eq('contact_id', contact_id).eq('status', 'completed').order('date', { ascending: false }).limit(3),
    ])

    if (contact) {
      clientContext = `\n\n## Active Client Context: ${contact.name} at ${contact.company}\n${contact.ai_summary || ''}`
    }
    if (memories && memories.length > 0) {
      clientContext += `\n\n## Client Memory:\n${memories.map(m => `- [${m.memory_type}] ${m.content}`).join('\n')}`
    }
    if (meetings && meetings.length > 0) {
      clientContext += `\n\n## Recent Meetings:\n${meetings.map(m => `- ${new Date(m.date).toLocaleDateString()}: ${m.ai_summary || m.key_insights || ''}`).join('\n')}`
    }
  }

  // Step 3: Build context from retrieved knowledge
  const knowledgeContext = knowledgeResults && knowledgeResults.length > 0
    ? `\n\n## Retrieved Knowledge:\n${knowledgeResults.map((r: { content: string; id: string }, i: number) => `[${i + 1}] ${r.content}`).join('\n\n')}`
    : '\n\n## Retrieved Knowledge:\nNo highly relevant items found in the knowledge base for this query.'

  const systemPrompt = buildSystemPrompt(
    `You are Kinetic, an AI co-pilot for an AI consulting practice. You answer questions by synthesizing knowledge from the consultant's knowledge base, meeting notes, and client context.

When citing sources, use numbered references like [1], [2] that correspond to the Retrieved Knowledge items.
If the knowledge base doesn't contain relevant information, say so clearly rather than fabricating an answer.
For Intelligence Layer prompt patterns, respond appropriately:
- "How would [role] see this?" → Perspective Shifting: model the stakeholder's likely viewpoint
- "What if [scenario]?" → Counterfactual: reason through the branching scenario
- "What am I wrong about?" → Intellectual Honesty: review tracked assumptions and surface contradictions
- "What patterns am I seeing?" → Pattern Recognition: synthesize across provided context
- "What's changed with [Client]?" → Temporal Intelligence: compare recent vs. historical context${clientContext}${knowledgeContext}`
  )

  // Step 4: Stream the response
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    async start(controller) {
      try {
        const anthropicMessages = [
          ...history.map((m: { role: string; content: string }) => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
          })),
          { role: 'user' as const, content: message },
        ]

        const response = await anthropic.messages.stream({
          model: 'claude-sonnet-4-5-20250929',
          max_tokens: 2000,
          system: systemPrompt,
          messages: anthropicMessages,
        })

        for await (const chunk of response) {
          if (
            chunk.type === 'content_block_delta' &&
            chunk.delta.type === 'text_delta'
          ) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ text: chunk.delta.text })}\n\n`))
          }
        }

        controller.enqueue(encoder.encode('data: [DONE]\n\n'))
        controller.close()
      } catch {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ error: 'Stream failed' })}\n\n`))
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  })
}
