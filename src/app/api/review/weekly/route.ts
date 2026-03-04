// src/app/api/review/weekly/route.ts
export const dynamic = 'force-dynamic'
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { callLLM } from '@/lib/anthropic'
import { buildSystemPrompt } from '@/lib/intelligence-layer'
import { weeklyReviewPrompt, type WeeklyReviewContext } from '@/lib/prompts/weekly-review'

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    // Default to current week (Sunday–Saturday)
    const now = new Date()
    const weekStart = new Date(now)
    weekStart.setDate(now.getDate() - now.getDay())
    weekStart.setHours(0, 0, 0, 0)

    const weekEnd = new Date(weekStart)
    weekEnd.setDate(weekStart.getDate() + 6)
    weekEnd.setHours(23, 59, 59, 999)

    const weekStartISO = (body.week_start ? new Date(body.week_start) : weekStart).toISOString()
    const weekEndISO = (body.week_end ? new Date(body.week_end) : weekEnd).toISOString()

    // Parallel fetch — batch all independent queries (best practice: avoid sequential round-trips)
    const [
      { data: meetings },
      { data: followUps },
      { data: knowledge },
      { data: patterns },
      { data: practiceMemory },
      { data: allContacts },
    ] = await Promise.all([
      supabase
        .from('meetings')
        .select('date, type, ai_summary, pain_points_mentioned, contacts(name, company)')
        .gte('date', weekStartISO)
        .lte('date', weekEndISO)
        .eq('status', 'completed'),
      supabase
        .from('follow_ups')
        .select('type, due_date, status, contacts(name)')
        .lte('due_date', weekEndISO)
        .in('status', ['pending', 'sent', 'skipped']),
      supabase
        .from('knowledge_items')
        .select('title, categories')
        .gte('created_at', weekStartISO)
        .lte('created_at', weekEndISO),
      supabase
        .from('patterns')
        .select('description, pattern_type, confidence')
        .eq('confidence', 'established')
        .order('last_reinforced', { ascending: false })
        .limit(5),
      supabase
        .from('practice_memory')
        .select('memory_type, content, created_at')
        .eq('is_active', true)
        .order('created_at', { ascending: false })
        .limit(10),
      supabase
        .from('contacts')
        .select('name, company, updated_at')
        .eq('relationship_status', 'active'),
    ])

    // Contacts with no activity in 21+ days
    const twentyOneDaysAgo = new Date()
    twentyOneDaysAgo.setDate(twentyOneDaysAgo.getDate() - 21)
    const neglectedContacts = (allContacts || [])
      .filter(c => new Date(c.updated_at) < twentyOneDaysAgo)
      .map(c => ({
        name: c.name,
        company: c.company || '',
        days_since_contact: Math.floor((Date.now() - new Date(c.updated_at).getTime()) / 86400000),
      }))

    // Check for enough historical data (5+ prior meetings)
    const { count: totalMeetings } = await supabase
      .from('meetings')
      .select('*', { count: 'exact', head: true })
      .lt('date', weekStartISO)

    const ctx: WeeklyReviewContext = {
      weekStart: new Date(weekStartISO).toLocaleDateString(),
      weekEnd: new Date(weekEndISO).toLocaleDateString(),
      meetingsThisWeek: (meetings || []).map(m => ({
        date: m.date,
        contact_name: (m.contacts as unknown as { name: string; company: string })?.name || 'Unknown',
        company: (m.contacts as unknown as { name: string; company: string })?.company || '',
        type: m.type,
        ai_summary: m.ai_summary,
        pain_points_mentioned: m.pain_points_mentioned || [],
      })),
      followUpsDue: (followUps || []).map(f => ({
        contact_name: (f.contacts as unknown as { name: string })?.name || 'Unknown',
        type: f.type,
        due_date: f.due_date,
        status: f.status,
      })),
      knowledgeAddedThisWeek: knowledge || [],
      activePatterns: patterns || [],
      practiceMemory: practiceMemory || [],
      hasEnoughHistoricalData: (totalMeetings || 0) > 5,
      neglectedContacts,
    }

    const systemPrompt = buildSystemPrompt(
      'You are Kinetic, generating a weekly review for a solo AI consultant. Be specific, grounded, and honest.'
    )

    const content = await callLLM({
      systemPrompt,
      userMessage: weeklyReviewPrompt(ctx),
      maxTokens: 3000,
    })

    return NextResponse.json({
      review: content,
      week_start: weekStartISO,
      week_end: weekEndISO,
      stats: {
        meetings: meetings?.length || 0,
        knowledge_items: knowledge?.length || 0,
        follow_ups_due: followUps?.length || 0,
        neglected_contacts: neglectedContacts.length,
      },
    })
  } catch (err) {
    console.error('POST /api/review/weekly error:', err)
    return NextResponse.json({ error: 'Failed to generate weekly review' }, { status: 500 })
  }
}
