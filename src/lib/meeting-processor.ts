// src/lib/meeting-processor.ts
import { callLLM } from './anthropic'
import { supabase } from './supabase'
import { createEmbedding, meetingEmbeddingText } from './embeddings'
import { buildMeetingProcessingPrompt } from './prompts/meeting-processing'
import { buildThankYouPrompt } from './prompts/thank-you'
import type { ActionItem } from '@/types'

interface ProcessedMeeting {
  summary: string
  essential_takeaway: string
  action_items: ActionItem[]
  pain_points_mentioned: string[]
  buying_signals: string[]
  key_insights: string
  assumptions_stated: string[]
  gaps_not_addressed: string
}

export function parseMeetingProcessingResponse(json: string): ProcessedMeeting {
  try {
    const parsed = JSON.parse(json)
    return {
      summary: parsed.summary ?? '',
      essential_takeaway: parsed.essential_takeaway ?? '',
      action_items: Array.isArray(parsed.action_items) ? parsed.action_items : [],
      pain_points_mentioned: Array.isArray(parsed.pain_points_mentioned) ? parsed.pain_points_mentioned : [],
      buying_signals: Array.isArray(parsed.buying_signals) ? parsed.buying_signals : [],
      key_insights: parsed.key_insights ?? '',
      assumptions_stated: Array.isArray(parsed.assumptions_stated) ? parsed.assumptions_stated : [],
      gaps_not_addressed: parsed.gaps_not_addressed ?? '',
    }
  } catch {
    return {
      summary: '',
      essential_takeaway: '',
      action_items: [],
      pain_points_mentioned: [],
      buying_signals: [],
      key_insights: '',
      assumptions_stated: [],
      gaps_not_addressed: '',
    }
  }
}

/**
 * Full AI processing chain for a completed meeting.
 * Called after meeting is saved to DB with raw_notes.
 *
 * Steps:
 * 1. Generate AI summary + extract action items, pain points, buying signals,
 *    assumptions (Intelligence Layer: Intellectual Honesty),
 *    and gaps not addressed (Intelligence Layer: Generative Questioning)
 * 2. Generate thank-you email draft
 * 3. Create follow-up records
 * 4. Embed the meeting
 * 5. Store extracted assumptions as client_memory entries
 */
export async function processMeeting(meetingId: string): Promise<void> {
  // Fetch meeting + contact
  const { data: meeting } = await supabase
    .from('meetings')
    .select('*, contacts(name, company)')
    .eq('id', meetingId)
    .single()

  if (!meeting || !meeting.raw_notes) return

  const contact = meeting.contacts as { name: string; company: string | null }

  // Step 1: Process meeting notes with LLM
  const { systemPrompt, userMessage } = buildMeetingProcessingPrompt({
    contactName: contact.name,
    contactCompany: contact.company,
    rawNotes: meeting.raw_notes,
  })
  const rawResponse = await callLLM({ systemPrompt, userMessage, maxTokens: 2048 })
  const processed = parseMeetingProcessingResponse(rawResponse)

  // Step 2: Generate thank-you draft
  const thankYouPrompts = buildThankYouPrompt({
    contactName: contact.name,
    meetingSummary: processed.summary,
    actionItems: processed.action_items,
    meetingType: meeting.type,
  })
  const thankYouDraft = await callLLM({
    systemPrompt: thankYouPrompts.systemPrompt,
    userMessage: thankYouPrompts.userMessage,
    maxTokens: 512,
  })

  // Step 3: Generate embedding
  const embeddingText = meetingEmbeddingText({
    raw_notes: meeting.raw_notes,
    ai_summary: processed.summary,
    pain_points_mentioned: processed.pain_points_mentioned,
    key_insights: processed.key_insights,
  })
  const embedding = await createEmbedding(embeddingText)

  // Step 4: Update meeting record with all processed data
  await supabase
    .from('meetings')
    .update({
      status: 'completed',
      ai_summary: processed.summary,
      action_items: processed.action_items,
      pain_points_mentioned: processed.pain_points_mentioned,
      buying_signals: processed.buying_signals,
      key_insights: `${processed.essential_takeaway}\n\n${processed.key_insights}\n\nGaps not addressed: ${processed.gaps_not_addressed}`,
      thank_you_draft: thankYouDraft,
      embedding,
    })
    .eq('id', meetingId)

  // Step 5: Create follow-up records
  const today = new Date()
  const followUps = []

  // Always create a thank-you follow-up
  followUps.push({
    contact_id: meeting.contact_id,
    meeting_id: meetingId,
    type: 'thank_you' as const,
    message_draft: thankYouDraft,
    due_date: new Date(today.getTime() + 24 * 60 * 60 * 1000)
      .toISOString()
      .split('T')[0],
    status: 'pending' as const,
  })

  // If buying signals detected, create a check-in follow-up
  if (processed.buying_signals.length > 0) {
    followUps.push({
      contact_id: meeting.contact_id,
      meeting_id: meetingId,
      type: 'check_in' as const,
      message_draft: null,
      due_date: new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)
        .toISOString()
        .split('T')[0],
      status: 'pending' as const,
    })
  }

  if (followUps.length > 0) {
    await supabase.from('follow_ups').insert(followUps)
  }

  // Step 6 (Intelligence Layer): Store extracted assumptions as client_memory
  if (processed.assumptions_stated.length > 0) {
    const memoryEntries = processed.assumptions_stated.map((assumption) => ({
      contact_id: meeting.contact_id,
      memory_type: 'assumption' as const,
      content: assumption,
      source_meeting_id: meetingId,
    }))
    await supabase.from('client_memory').insert(memoryEntries)
  }
}
