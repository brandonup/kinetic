// src/app/api/follow-ups/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

// GET /api/follow-ups — list pending follow-ups, sorted by due date
// Optional: ?status=pending|sent|skipped&contact_id=<uuid>
export async function GET(request: NextRequest) {
  try {
    const status = request.nextUrl.searchParams.get('status') ?? 'pending'
    const contactId = request.nextUrl.searchParams.get('contact_id')

    let query = supabase
      .from('follow_ups')
      .select('*, contacts(name, company, email)')
      .eq('status', status)
      .order('due_date', { ascending: true })

    if (contactId) query = query.eq('contact_id', contactId)

    const { data, error } = await query
    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/follow-ups error:', err)
    return NextResponse.json({ error: 'Failed to fetch follow-ups' }, { status: 500 })
  }
}
