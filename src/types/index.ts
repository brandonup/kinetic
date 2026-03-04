// src/types/index.ts

export type RelationshipStatus = 'new' | 'warm' | 'active' | 'dormant'
export type MeetingStatus = 'upcoming' | 'completed' | 'cancelled'
export type MeetingType = 'networking' | 'discovery_call' | 'follow_up' | 'coffee_chat' | 'event' | 'other'
export type KnowledgeSourceType = 'article' | 'youtube_transcript' | 'podcast_transcript' | 'video_transcript' | 'research_paper' | 'personal_note' | 'book_notes' | 'other'
export type OpportunityStatus = 'identified' | 'exploring' | 'proposal_sent' | 'won' | 'lost' | 'on_hold'
export type FollowUpType = 'thank_you' | 'check_in' | 'share_resource' | 'intro_request' | 'proposal' | 'custom'
export type FollowUpStatus = 'pending' | 'sent' | 'skipped'
export type ClientMemoryType = 'goal' | 'preference' | 'decision' | 'org_dynamic' | 'project_status' | 'constraint' | 'assumption' | 'hypothesis' | 'other'
export type PracticeMemoryType = 'framework' | 'positioning' | 'pricing' | 'lesson_learned' | 'market_observation' | 'methodology' | 'pattern_observed' | 'drift_detected' | 'bias_noted' | 'other'
export type QuickCaptureSource = 'slack' | 'mcp_claude' | 'mcp_chatgpt' | 'mcp_cursor' | 'mcp_other' | 'web'
export type PatternType = 'cross_client' | 'market_trend' | 'behavioral' | 'knowledge_gap'
export type PatternConfidence = 'emerging' | 'established' | 'fading'
export type AgentTriggerType = 'event' | 'cron' | 'on_demand'
export type AgentStatus = 'running' | 'complete' | 'failed'

export interface Contact {
  id: string
  name: string
  email: string | null
  phone: string | null
  company: string | null
  title: string | null
  linkedin_url: string | null
  location: string | null
  tags: string[]
  relationship_status: RelationshipStatus
  ai_summary: string
  source: string
  notes: string
  icp_fit_score: number | null
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface Meeting {
  id: string
  contact_id: string
  date: string
  status: MeetingStatus
  type: MeetingType
  location: string | null
  raw_notes: string | null
  ai_summary: string | null
  action_items: ActionItem[] | null
  key_insights: string | null
  pain_points_mentioned: string[]
  buying_signals: string[]
  thank_you_draft: string | null
  client_facing_summary: string | null
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface ActionItem {
  text: string
  due_date: string | null
  priority: 'high' | 'medium' | 'low'
}

export interface FollowUp {
  id: string
  contact_id: string
  meeting_id: string | null
  due_date: string
  type: FollowUpType
  message_draft: string | null
  status: FollowUpStatus
  created_at: string
}

export interface KnowledgeItem {
  id: string
  title: string
  source_url: string | null
  source_type: KnowledgeSourceType
  raw_content: string
  ai_summary: string
  key_takeaways: string[]
  categories: string[]
  relevance_tags: string[]
  embedding: number[] | null
  created_at: string
}

export interface Opportunity {
  id: string
  contact_id: string
  title: string
  status: OpportunityStatus
  service_type: string | null
  estimated_value: number | null
  evidence: string
  next_step: string
  created_at: string
  updated_at: string
}

export interface ClientMemory {
  id: string
  contact_id: string
  memory_type: ClientMemoryType
  content: string
  source_meeting_id: string | null
  is_active: boolean
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface PracticeMemory {
  id: string
  memory_type: PracticeMemoryType
  content: string
  context: string | null
  is_active: boolean
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface Pattern {
  id: string
  pattern_type: PatternType
  description: string
  evidence: Array<{ type: string; id: string }>
  affected_contacts: string[]
  confidence: PatternConfidence
  first_detected: string
  last_reinforced: string
  embedding: number[] | null
  created_at: string
}

export interface PrepBrief {
  id: string
  meeting_id: string
  contact_id: string
  content: string
  recent_news: string | null
  research_complete: boolean
  generated_at: string
  updated_at: string
}

export interface AgentRun {
  id: string
  agent_name: string
  trigger_type: AgentTriggerType
  trigger_ref: string | null
  status: AgentStatus
  steps_completed: number
  steps_total: number
  errors: unknown | null
  output_summary: string | null
  created_at: string
  completed_at: string | null
}

export interface QuickCapture {
  id: string
  content: string
  embedding: number[] | null
  source_channel: QuickCaptureSource
  metadata: {
    category?: string
    people_mentioned?: string[]
    action_items?: string[]
    tags?: string[]
  }
  linked_contact_id: string | null
  promoted_to: string | null
  created_at: string
}

export interface SearchResult {
  id: string
  source_table: string
  content: string
  metadata: Record<string, unknown>
  similarity: number
}
