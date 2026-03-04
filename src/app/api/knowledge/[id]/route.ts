// src/app/api/knowledge/[id]/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { data, error } = await supabase
      .from('knowledge_items')
      .select('*, knowledge_chunks(chunk_index, content)')
      .eq('id', id)
      .single()
    if (error) return NextResponse.json({ error: error.message }, { status: 404 })
    return NextResponse.json({ item: data })
  } catch (err) {
    console.error('GET /api/knowledge/[id] error:', err)
    return NextResponse.json({ error: 'Failed to fetch knowledge item' }, { status: 500 })
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    // Chunks are cascade deleted via FK
    const { error } = await supabase.from('knowledge_items').delete().eq('id', id)
    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ success: true })
  } catch (err) {
    console.error('DELETE /api/knowledge/[id] error:', err)
    return NextResponse.json({ error: 'Failed to delete knowledge item' }, { status: 500 })
  }
}
