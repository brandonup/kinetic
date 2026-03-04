// src/app/api/practice/memory/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { createEmbedding } from '@/lib/embeddings'
import type { PracticeMemoryType } from '@/types'

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const type = searchParams.get('type') as PracticeMemoryType | null
    const activeOnly = searchParams.get('active') !== 'false'

    let query = supabase
      .from('practice_memory')
      .select('id, memory_type, content, context, is_active, created_at, updated_at')
      .order('created_at', { ascending: false })

    if (activeOnly) query = query.eq('is_active', true)
    if (type) query = query.eq('memory_type', type)

    const { data, error } = await query
    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ memory: data || [] })
  } catch (err) {
    console.error('GET /api/practice/memory error:', err)
    return NextResponse.json({ error: 'Failed to fetch practice memory' }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { memory_type, content, context } = body

    if (!memory_type || !content) {
      return NextResponse.json({ error: 'memory_type and content required' }, { status: 400 })
    }

    const embedding = await createEmbedding(content)

    const { data, error } = await supabase
      .from('practice_memory')
      .insert({ memory_type, content, context: context || null, embedding })
      .select('id, memory_type, content, context, is_active, created_at')
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ memory: data }, { status: 201 })
  } catch (err) {
    console.error('POST /api/practice/memory error:', err)
    return NextResponse.json({ error: 'Failed to create practice memory' }, { status: 500 })
  }
}
