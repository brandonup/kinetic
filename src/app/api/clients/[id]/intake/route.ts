// src/app/api/clients/[id]/intake/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { createEmbedding } from '@/lib/embeddings'

interface IntakePayload {
  goals: string[]
  constraints: string[]
  pain_points: string[]
  industry_context: string
  decision_makers: string
  current_tools: string
  success_definition: string
  timeline: string
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body: IntakePayload = await req.json()

    const memoryItems = [
      ...body.goals.filter(Boolean).map(g => ({ memory_type: 'goal' as const, content: g })),
      ...body.constraints.filter(Boolean).map(c => ({ memory_type: 'constraint' as const, content: c })),
      ...body.pain_points.filter(Boolean).map(p => ({ memory_type: 'other' as const, content: `Pain point: ${p}` })),
      body.industry_context && { memory_type: 'other' as const, content: `Industry context: ${body.industry_context}` },
      body.decision_makers && { memory_type: 'org_dynamic' as const, content: `Decision makers: ${body.decision_makers}` },
      body.current_tools && { memory_type: 'preference' as const, content: `Current tools: ${body.current_tools}` },
      body.success_definition && { memory_type: 'goal' as const, content: `Success definition: ${body.success_definition}` },
      body.timeline && { memory_type: 'constraint' as const, content: `Timeline: ${body.timeline}` },
    ].filter(Boolean) as { memory_type: string; content: string }[]

    if (memoryItems.length === 0) {
      return NextResponse.json({ error: 'No intake data provided' }, { status: 400 })
    }

    // Embed all items in parallel — best practice: batch concurrent embedding calls
    const records = await Promise.all(
      memoryItems.map(async item => ({
        contact_id: id,
        memory_type: item.memory_type,
        content: item.content,
        embedding: await createEmbedding(item.content),
      }))
    )

    const { data, error } = await supabase
      .from('client_memory')
      .insert(records)
      .select('id, memory_type, content, created_at')

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })

    // Promote contact to 'active' after intake
    await supabase
      .from('contacts')
      .update({ relationship_status: 'active', updated_at: new Date().toISOString() })
      .eq('id', id)

    return NextResponse.json({ created: data?.length || 0, memory: data }, { status: 201 })
  } catch (err) {
    console.error('POST /api/clients/[id]/intake error:', err)
    return NextResponse.json({ error: 'Failed to save intake' }, { status: 500 })
  }
}
