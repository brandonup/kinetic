// src/app/api/contacts/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { callLLM } from '@/lib/anthropic'
import { createEmbedding, contactEmbeddingText } from '@/lib/embeddings'
import { buildContactSummaryPrompt } from '@/lib/prompts/contact-summary'
import type { CreateContactRequest } from '@/types/api'

// GET /api/contacts — list all contacts, optional ?search= query
export async function GET(request: NextRequest) {
  try {
    const searchQuery = request.nextUrl.searchParams.get('search')

    if (searchQuery) {
      // Semantic search: embed the query, then match_documents
      const queryEmbedding = await createEmbedding(searchQuery)
      const { data, error } = await supabase.rpc('match_documents', {
        query_embedding: queryEmbedding,
        match_threshold: 0.4,
        match_count: 20,
        filter_source: 'contacts',
      })
      if (error) throw error

      // Fetch full contact records for the matched IDs
      const ids = (data ?? []).map((r: { id: string }) => r.id)
      if (ids.length === 0) return NextResponse.json([])

      const { data: contacts, error: contactsError } = await supabase
        .from('contacts')
        .select('*')
        .in('id', ids)
        .order('updated_at', { ascending: false })

      if (contactsError) throw contactsError
      return NextResponse.json(contacts)
    }

    // Default: return all contacts sorted by recently updated
    const { data, error } = await supabase
      .from('contacts')
      .select('*')
      .order('updated_at', { ascending: false })

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/contacts error:', err)
    return NextResponse.json({ error: 'Failed to fetch contacts' }, { status: 500 })
  }
}

// POST /api/contacts — create a new contact
export async function POST(request: NextRequest) {
  try {
    const body: CreateContactRequest = await request.json()

    if (!body.name?.trim()) {
      return NextResponse.json({ error: 'name is required' }, { status: 400 })
    }

    // Generate AI summary
    const { systemPrompt, userMessage } = buildContactSummaryPrompt({
      name: body.name,
      company: body.company,
      title: body.title,
      location: body.location,
      source: body.source,
      notes: body.notes,
    })
    const aiSummary = await callLLM({ systemPrompt, userMessage, maxTokens: 512 })

    // Generate embedding from combined contact text
    const embeddingText = contactEmbeddingText({
      name: body.name,
      company: body.company,
      title: body.title,
      ai_summary: aiSummary,
      notes: body.notes,
      tags: body.tags,
    })
    const embedding = await createEmbedding(embeddingText)

    const { data, error } = await supabase
      .from('contacts')
      .insert({
        name: body.name.trim(),
        email: body.email ?? null,
        phone: body.phone ?? null,
        company: body.company ?? null,
        title: body.title ?? null,
        linkedin_url: body.linkedin_url ?? null,
        location: body.location ?? null,
        source: body.source ?? '',
        notes: body.notes ?? '',
        tags: body.tags ?? [],
        ai_summary: aiSummary,
        embedding,
        relationship_status: 'new',
      })
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data, { status: 201 })
  } catch (err) {
    console.error('POST /api/contacts error:', err)
    return NextResponse.json({ error: 'Failed to create contact' }, { status: 500 })
  }
}
