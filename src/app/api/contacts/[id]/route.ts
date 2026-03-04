// src/app/api/contacts/[id]/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { createEmbedding, contactEmbeddingText } from '@/lib/embeddings'
import type { UpdateContactRequest } from '@/types/api'

// GET /api/contacts/:id
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { data, error } = await supabase
      .from('contacts')
      .select('*')
      .eq('id', id)
      .single()

    if (error) {
      if (error.code === 'PGRST116') {
        return NextResponse.json({ error: 'Contact not found' }, { status: 404 })
      }
      throw error
    }
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/contacts/[id] error:', err)
    return NextResponse.json({ error: 'Failed to fetch contact' }, { status: 500 })
  }
}

// PUT /api/contacts/:id
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body: UpdateContactRequest = await request.json()

    // Re-embed if name, company, title, or notes changed
    const shouldReEmbed = body.name || body.company || body.title || body.notes

    let embedding: number[] | undefined
    if (shouldReEmbed) {
      // Fetch current contact to merge
      const { data: current } = await supabase
        .from('contacts')
        .select('name, company, title, ai_summary, notes, tags')
        .eq('id', id)
        .single()

      if (current) {
        const embeddingText = contactEmbeddingText({
          name: body.name ?? current.name,
          company: body.company ?? current.company,
          title: body.title ?? current.title,
          ai_summary: current.ai_summary,
          notes: body.notes ?? current.notes,
          tags: body.tags ?? current.tags,
        })
        embedding = await createEmbedding(embeddingText)
      }
    }

    const { data, error } = await supabase
      .from('contacts')
      .update({ ...body, ...(embedding ? { embedding } : {}) })
      .eq('id', id)
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('PUT /api/contacts/[id] error:', err)
    return NextResponse.json({ error: 'Failed to update contact' }, { status: 500 })
  }
}

// DELETE /api/contacts/:id
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { error } = await supabase.from('contacts').delete().eq('id', id)
    if (error) throw error
    return NextResponse.json({ success: true })
  } catch (err) {
    console.error('DELETE /api/contacts/[id] error:', err)
    return NextResponse.json({ error: 'Failed to delete contact' }, { status: 500 })
  }
}
