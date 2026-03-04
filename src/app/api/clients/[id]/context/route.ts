// src/app/api/clients/[id]/context/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { createEmbedding } from '@/lib/embeddings'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params

    // Parallel fetch — avoid sequential round-trips (best practice: batch independent queries)
    const [
      { data: contact },
      { data: memories },
      { data: meetings },
      { data: followUps },
    ] = await Promise.all([
      supabase
        .from('contacts')
        .select('id, name, company, title, email, relationship_status, ai_summary, tags, icp_fit_score, notes, created_at, updated_at')
        .eq('id', id)
        .single(),
      supabase
        .from('client_memory')
        .select('id, memory_type, content, source_meeting_id, is_active, created_at')
        .eq('contact_id', id)
        .eq('is_active', true)
        .order('created_at', { ascending: false }),
      supabase
        .from('meetings')
        .select('id, date, type, status, ai_summary, key_insights, pain_points_mentioned, buying_signals, follow_ups(id, type, status, due_date)')
        .eq('contact_id', id)
        .order('date', { ascending: false })
        .limit(5),
      supabase
        .from('follow_ups')
        .select('id, type, due_date, message_draft, status')
        .eq('contact_id', id)
        .eq('status', 'pending')
        .order('due_date', { ascending: true }),
    ])

    if (!contact) return NextResponse.json({ error: 'Contact not found' }, { status: 404 })

    // Semantic search: find knowledge relevant to this client's context
    // Use goals + summary as the search anchor
    const searchText = [
      contact.ai_summary,
      memories?.filter(m => m.memory_type === 'goal').map(m => m.content).join(' '),
    ].filter(Boolean).join(' ')

    let relevantKnowledge: unknown[] = []
    if (searchText.trim()) {
      const embedding = await createEmbedding(searchText)
      const { data: knowledgeHits } = await supabase.rpc('match_documents', {
        query_embedding: embedding,
        match_threshold: 0.45,
        match_count: 5,
        filter_source: 'knowledge_items',
      })
      relevantKnowledge = knowledgeHits || []
    }

    return NextResponse.json({
      contact,
      memory: memories || [],
      meetings: meetings || [],
      follow_ups: followUps || [],
      relevant_knowledge: relevantKnowledge,
    })
  } catch (err) {
    console.error('GET /api/clients/[id]/context error:', err)
    return NextResponse.json({ error: 'Failed to fetch client context' }, { status: 500 })
  }
}
