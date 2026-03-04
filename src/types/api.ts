// src/types/api.ts
// Request/response shapes for API routes

export interface CreateContactRequest {
  name: string
  email?: string
  phone?: string
  company?: string
  title?: string
  linkedin_url?: string
  location?: string
  source?: string
  notes?: string
  tags?: string[]
}

export interface UpdateContactRequest {
  name?: string
  email?: string
  phone?: string
  company?: string
  title?: string
  linkedin_url?: string
  location?: string
  source?: string
  notes?: string
  tags?: string[]
  relationship_status?: import('./index').RelationshipStatus
  icp_fit_score?: number
}

export interface CreateMeetingRequest {
  contact_id: string
  date: string
  type?: import('./index').MeetingType
  location?: string
  status?: import('./index').MeetingStatus
  raw_notes?: string
}

export interface UpdateFollowUpRequest {
  status: import('./index').FollowUpStatus
}

export interface ApiError {
  error: string
  details?: string
}
