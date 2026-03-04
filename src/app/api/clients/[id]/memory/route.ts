// src/app/api/clients/[id]/memory/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { createEmbedding } from '@/lib/embeddings'
import type { ClientMemoryType } from '@/types'

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(req.url)
    const type = searchParams.get('type') as ClientMemoryType | null
    const activeOnly = searchParams.get('active') !== 'false'

    let query = supabase
      .from('client_memory')
      .select('id, contact_id, memory_type, content, source_meeting_id, is_active, created_at, updated_at')
      .eq('contact_id', id)
      .order('created_at', { ascending: false })

    if (activeOnly) query = query.eq('is_active', true)
    if (type) query = query.eq('memory_type', type)

    const { data, error } = await query
    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ memory: data || [] })
  } catch (err) {
    console.error('GET /api/clients/[id]/memory error:', err)
    return NextResponse.json({ error: 'Failed to fetch client memory' }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await req.json()
    const { memory_type, content, source_meeting_id } = body

    if (!memory_type || !content) {
      return NextResponse.json({ error: 'memory_type and content required' }, { status: 400 })
    }

    const embedding = await createEmbedding(content)

    const { data, error } = await supabase
      .from('client_memory')
      .insert({
        contact_id: id,
        memory_type,
        content,
        source_meeting_id: source_meeting_id || null,
        embedding,
      })
      .select('id, contact_id, memory_type, content, source_meeting_id, is_active, created_at')
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ memory: data }, { status: 201 })
  } catch (err) {
    console.error('POST /api/clients/[id]/memory error:', err)
    return NextResponse.json({ error: 'Failed to create client memory' }, { status: 500 })
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await req.json()
    const { memory_id, is_active } = body

    const { data, error } = await supabase
      .from('client_memory')
      .update({ is_active, updated_at: new Date().toISOString() })
      .eq('id', memory_id)
      .eq('contact_id', id)
      .select('id, memory_type, content, is_active, updated_at')
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ memory: data })
  } catch (err) {
    console.error('PUT /api/clients/[id]/memory error:', err)
    return NextResponse.json({ error: 'Failed to update client memory' }, { status: 500 })
  }
}
