// src/app/api/summary/client-facing/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { callLLM } from '@/lib/anthropic'
import { buildSystemPrompt } from '@/lib/intelligence-layer'
import { clientFacingSummaryPrompt } from '@/lib/prompts/prep-brief'

export async function POST(req: NextRequest) {
  try {
    const { meeting_id } = await req.json()
    if (!meeting_id) return NextResponse.json({ error: 'meeting_id required' }, { status: 400 })

    const { data: meeting, error: meetingError } = await supabase
      .from('meetings')
      .select('id, type, date, raw_notes, contacts(name, company)')
      .eq('id', meeting_id)
      .single()

    if (meetingError || !meeting) return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
    if (!meeting.raw_notes) return NextResponse.json({ error: 'No meeting notes to summarize' }, { status: 422 })

    const contact = meeting.contacts as unknown as { name: string; company: string }
    const meetingContext = `${meeting.type} with ${contact.name} at ${contact.company} on ${new Date(meeting.date).toLocaleDateString()}`

    const systemPrompt = buildSystemPrompt(
      'You generate professional, client-safe meeting summaries for an AI consultant.'
    )

    const content = await callLLM({
      systemPrompt,
      userMessage: clientFacingSummaryPrompt(meeting.raw_notes, meetingContext),
      model: 'claude-haiku-4-5-20251001',
      maxTokens: 800,
    })

    const { error: updateError } = await supabase
      .from('meetings')
      .update({ client_facing_summary: content, updated_at: new Date().toISOString() })
      .eq('id', meeting_id)

    if (updateError) return NextResponse.json({ error: updateError.message }, { status: 500 })
    return NextResponse.json({ summary: content })
  } catch (err) {
    console.error('POST /api/summary/client-facing error:', err)
    return NextResponse.json({ error: 'Failed to generate client-facing summary' }, { status: 500 })
  }
}
