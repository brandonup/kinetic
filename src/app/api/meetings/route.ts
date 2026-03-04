// src/app/api/meetings/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { processMeeting } from '@/lib/meeting-processor'
import type { CreateMeetingRequest } from '@/types/api'

// GET /api/meetings
export async function GET(request: NextRequest) {
  try {
    const contactId = request.nextUrl.searchParams.get('contact_id')
    const status = request.nextUrl.searchParams.get('status')

    let query = supabase
      .from('meetings')
      .select('*, contacts(name, company)')
      .order('date', { ascending: false })

    if (contactId) query = query.eq('contact_id', contactId)
    if (status) query = query.eq('status', status)

    const { data, error } = await query
    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/meetings error:', err)
    return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
  }
}

// POST /api/meetings
export async function POST(request: NextRequest) {
  try {
    const body: CreateMeetingRequest = await request.json()

    if (!body.contact_id) {
      return NextResponse.json({ error: 'contact_id is required' }, { status: 400 })
    }
    if (!body.date) {
      return NextResponse.json({ error: 'date is required' }, { status: 400 })
    }

    const isCompleted = body.status === 'completed' && body.raw_notes

    // Insert meeting record
    const { data: meeting, error } = await supabase
      .from('meetings')
      .insert({
        contact_id: body.contact_id,
        date: body.date,
        type: body.type ?? 'other',
        location: body.location ?? null,
        status: isCompleted ? 'completed' : (body.status ?? 'upcoming'),
        raw_notes: body.raw_notes ?? null,
      })
      .select()
      .single()

    if (error) throw error

    // Trigger AI processing synchronously if notes provided
    // Note: In Phase 2 this moves to the Post-Meeting Agent (Edge Function).
    if (isCompleted && body.raw_notes) {
      await processMeeting(meeting.id)
      // Re-fetch to get the processed version
      const { data: processed } = await supabase
        .from('meetings')
        .select('*')
        .eq('id', meeting.id)
        .single()
      return NextResponse.json(processed, { status: 201 })
    }

    return NextResponse.json(meeting, { status: 201 })
  } catch (err) {
    console.error('POST /api/meetings error:', err)
    return NextResponse.json({ error: 'Failed to create meeting' }, { status: 500 })
  }
}
