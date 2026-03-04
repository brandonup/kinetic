// src/app/api/meetings/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { processMeeting } from '@/lib/meeting-processor'

// GET /api/meetings/:id
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { data, error } = await supabase
      .from('meetings')
      .select('*, contacts(name, company), follow_ups(*)')
      .eq('id', id)
      .single()

    if (error) {
      if (error.code === 'PGRST116') {
        return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
      }
      throw error
    }
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/meetings/[id] error:', err)
    return NextResponse.json({ error: 'Failed to fetch meeting' }, { status: 500 })
  }
}

// PUT /api/meetings/:id — used to add notes to an upcoming meeting (transitions to completed)
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()

    const { data: existing } = await supabase
      .from('meetings')
      .select('status')
      .eq('id', id)
      .single()

    const isTransitioningToCompleted =
      existing?.status === 'upcoming' && body.raw_notes

    const { data, error } = await supabase
      .from('meetings')
      .update({
        ...body,
        ...(isTransitioningToCompleted ? { status: 'completed' } : {}),
      })
      .eq('id', id)
      .select()
      .single()

    if (error) throw error

    // Trigger processing if transitioning from upcoming → completed with notes
    if (isTransitioningToCompleted) {
      await processMeeting(id)
      const { data: processed } = await supabase
        .from('meetings')
        .select('*')
        .eq('id', id)
        .single()
      return NextResponse.json(processed)
    }

    return NextResponse.json(data)
  } catch (err) {
    console.error('PUT /api/meetings/[id] error:', err)
    return NextResponse.json({ error: 'Failed to update meeting' }, { status: 500 })
  }
}
