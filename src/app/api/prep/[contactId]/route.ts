// src/app/api/prep/[contactId]/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { callLLM } from '@/lib/anthropic'
import { buildSystemPrompt } from '@/lib/intelligence-layer'
import { createEmbedding } from '@/lib/embeddings'
import { prepBriefPrompt, type PrepBriefContext } from '@/lib/prompts/prep-brief'

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ contactId: string }> }
) {
  try {
    const { contactId } = await params
    const body = await req.json()
    const { meeting_id } = body

    // Parallel fetch — batch independent queries (best practice)
    const [
      { data: contact },
      { data: memories },
      { data: meetings },
    ] = await Promise.all([
      supabase
        .from('contacts')
        .select('id, name, company, title, ai_summary, relationship_status')
        .eq('id', contactId)
        .single(),
      supabase
        .from('client_memory')
        .select('memory_type, content, created_at')
        .eq('contact_id', contactId)
        .eq('is_active', true),
      supabase
        .from('meetings')
        .select('date, ai_summary, key_insights, pain_points_mentioned')
        .eq('contact_id', contactId)
        .eq('status', 'completed')
        .order('date', { ascending: false })
        .limit(5),
    ])

    if (!contact) return NextResponse.json({ error: 'Contact not found' }, { status: 404 })

    // Semantic search for relevant knowledge
    const searchText = [
      contact.ai_summary,
      memories?.filter(m => m.memory_type === 'goal').map(m => m.content).join(' '),
      meetings?.[0]?.pain_points_mentioned?.join(' '),
    ].filter(Boolean).join(' ')

    let relevantKnowledge: Array<{ content: string }> = []
    if (searchText.trim()) {
      const embedding = await createEmbedding(searchText)
      const { data: hits } = await supabase.rpc('match_documents', {
        query_embedding: embedding,
        match_threshold: 0.45,
        match_count: 5,
        filter_source: 'knowledge_items',
      })
      relevantKnowledge = hits || []
    }

    // Get meeting details if provided
    let meetingDetails: { date: string; type: string } | undefined
    if (meeting_id) {
      const { data: meeting } = await supabase
        .from('meetings')
        .select('date, type')
        .eq('id', meeting_id)
        .single()
      if (meeting) meetingDetails = meeting
    }

    const ctx: PrepBriefContext = {
      contact: {
        name: contact.name,
        company: contact.company || '',
        title: contact.title,
        ai_summary: contact.ai_summary,
        relationship_status: contact.relationship_status,
      },
      meeting: meetingDetails,
      recentMeetings: (meetings || []).slice(0, 3).map(m => ({
        date: m.date,
        ai_summary: m.ai_summary,
        key_insights: m.key_insights,
        pain_points_mentioned: m.pain_points_mentioned || [],
      })),
      clientMemory: memories || [],
      relevantKnowledge,
      previousMeetingCount: meetings?.length || 0,
    }

    const systemPrompt = buildSystemPrompt(
      'You are Kinetic, an AI co-pilot for an AI consulting practice. Generate precise, grounded prep briefs.'
    )

    const content = await callLLM({
      systemPrompt,
      userMessage: prepBriefPrompt(ctx),
      maxTokens: 2500,
    })

    // Upsert into prep_briefs — conflict on meeting_id to avoid duplicates
    const { data: brief, error } = await supabase
      .from('prep_briefs')
      .upsert(
        {
          contact_id: contactId,
          meeting_id: meeting_id || null,
          content,
          generated_at: new Date().toISOString(),
        },
        { onConflict: 'meeting_id' }
      )
      .select()
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ brief }, { status: 201 })
  } catch (err) {
    console.error('POST /api/prep/[contactId] error:', err)
    return NextResponse.json({ error: 'Failed to generate prep brief' }, { status: 500 })
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ contactId: string }> }
) {
  try {
    const { contactId } = await params
    const { searchParams } = new URL(req.url)
    const meeting_id = searchParams.get('meeting_id')

    let query = supabase
      .from('prep_briefs')
      .select('id, contact_id, meeting_id, content, research_complete, generated_at, updated_at')
      .eq('contact_id', contactId)

    if (meeting_id) query = query.eq('meeting_id', meeting_id)

    const { data, error } = await query
      .order('generated_at', { ascending: false })
      .limit(1)
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 404 })
    return NextResponse.json({ brief: data })
  } catch (err) {
    console.error('GET /api/prep/[contactId] error:', err)
    return NextResponse.json({ error: 'Failed to fetch prep brief' }, { status: 500 })
  }
}
