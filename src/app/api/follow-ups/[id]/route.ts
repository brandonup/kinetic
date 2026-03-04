// src/app/api/follow-ups/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

// PUT /api/follow-ups/:id — update status (mark sent, skipped, back to pending)
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()

    const allowed = ['pending', 'sent', 'skipped']
    if (body.status && !allowed.includes(body.status)) {
      return NextResponse.json(
        { error: `status must be one of: ${allowed.join(', ')}` },
        { status: 400 }
      )
    }

    const { data, error } = await supabase
      .from('follow_ups')
      .update(body)
      .eq('id', id)
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('PUT /api/follow-ups/[id] error:', err)
    return NextResponse.json({ error: 'Failed to update follow-up' }, { status: 500 })
  }
}
