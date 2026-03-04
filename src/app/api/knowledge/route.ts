// src/app/api/knowledge/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { callLLM } from '@/lib/anthropic'
import { buildSystemPrompt } from '@/lib/intelligence-layer'
import { createEmbedding } from '@/lib/embeddings'
import {
  isYouTubeUrl,
  extractYouTubeVideoId,
  fetchYouTubeTranscript,
  fetchUrlContent,
  chunkText,
  buildKnowledgeEmbeddingText,
} from '@/lib/knowledge-processor'
import {
  knowledgeProcessingPrompt,
  parseKnowledgeProcessingResponse,
} from '@/lib/prompts/knowledge-processing'
import type { KnowledgeSourceType } from '@/types'

// GET /api/knowledge — list knowledge items, optional ?q= for semantic search
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const q = searchParams.get('q')
    const limit = parseInt(searchParams.get('limit') || '20')

    if (q) {
      // Semantic search via match_documents
      const embedding = await createEmbedding(q)
      const { data, error } = await supabase.rpc('match_documents', {
        query_embedding: embedding,
        match_threshold: 0.4,
        match_count: limit,
        filter_source: 'knowledge_items',
      })
      if (error) return NextResponse.json({ error: error.message }, { status: 500 })
      return NextResponse.json({ items: data || [] })
    }

    const { data, error } = await supabase
      .from('knowledge_items')
      .select('id, title, source_type, categories, relevance_tags, ai_summary, created_at')
      .order('created_at', { ascending: false })
      .limit(limit)
    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ items: data || [] })
  } catch (err) {
    console.error('GET /api/knowledge error:', err)
    return NextResponse.json({ error: 'Failed to fetch knowledge items' }, { status: 500 })
  }
}

// POST /api/knowledge — ingest a new knowledge item
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { source_url, raw_content, source_type: providedSourceType } = body

    if (!source_url && !raw_content) {
      return NextResponse.json({ error: 'source_url or raw_content required' }, { status: 400 })
    }

    let rawContent = raw_content || ''
    let sourceType: KnowledgeSourceType = providedSourceType || 'other'
    let inferredTitle = ''

    // Step 1: Fetch content based on input type
    if (source_url) {
      if (isYouTubeUrl(source_url)) {
        const videoId = extractYouTubeVideoId(source_url)
        if (!videoId) return NextResponse.json({ error: 'Invalid YouTube URL' }, { status: 400 })
        try {
          rawContent = await fetchYouTubeTranscript(videoId)
          sourceType = 'youtube_transcript'
        } catch {
          return NextResponse.json(
            { error: 'No transcript available for this video. Please try a different video or paste the content manually.' },
            { status: 422 }
          )
        }
      } else {
        const { title, content } = await fetchUrlContent(source_url)
        rawContent = content
        inferredTitle = title
        sourceType = sourceType === 'other' ? 'article' : sourceType
      }
    }

    if (!rawContent || rawContent.trim().length < 50) {
      return NextResponse.json({ error: 'Content too short to process' }, { status: 422 })
    }

    // Step 2: AI classification and summarization
    const systemPrompt = buildSystemPrompt(
      'You are a knowledge extraction specialist for an AI consulting practice.'
    )
    const llmResponse = await callLLM({
      systemPrompt,
      userMessage: knowledgeProcessingPrompt(rawContent, sourceType),
      model: 'claude-haiku-4-5-20251001',
      maxTokens: 1500,
    })

    const processed = parseKnowledgeProcessingResponse(llmResponse)
    const title = processed.title || inferredTitle || 'Untitled'

    // Step 3: Create the knowledge item record
    const embeddingText = buildKnowledgeEmbeddingText({
      title,
      ai_summary: processed.ai_summary,
      key_takeaways: processed.key_takeaways,
    })
    const embedding = await createEmbedding(embeddingText)

    const { data: item, error: insertError } = await supabase
      .from('knowledge_items')
      .insert({
        title,
        source_url: source_url || null,
        source_type: sourceType,
        raw_content: rawContent,
        ai_summary: processed.ai_summary,
        key_takeaways: processed.key_takeaways,
        categories: processed.categories,
        relevance_tags: processed.relevance_tags,
        embedding,
      })
      .select()
      .single()

    if (insertError) return NextResponse.json({ error: insertError.message }, { status: 500 })

    // Step 4: Chunk long content and store in knowledge_chunks
    if (rawContent.length > 2000) {
      const chunks = chunkText(rawContent, 2000, 200)
      const chunkRecords = await Promise.all(
        chunks.map(async (chunkContent, idx) => ({
          knowledge_item_id: item.id,
          chunk_index: idx,
          content: chunkContent,
          embedding: await createEmbedding(chunkContent),
        }))
      )
      await supabase.from('knowledge_chunks').insert(chunkRecords)
    }

    return NextResponse.json({ item }, { status: 201 })
  } catch (err) {
    console.error('POST /api/knowledge error:', err)
    return NextResponse.json({ error: 'Failed to ingest knowledge item' }, { status: 500 })
  }
}
