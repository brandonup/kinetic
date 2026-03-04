// src/types/index.test.ts
import { describe, it, expect } from 'vitest'
import type { Contact, Meeting, FollowUp } from './index'

describe('types', () => {
  it('Contact type has required fields', () => {
    const contact: Contact = {
      id: 'test-id',
      name: 'Jane Smith',
      email: null,
      phone: null,
      company: 'Acme',
      title: null,
      linkedin_url: null,
      location: null,
      tags: [],
      relationship_status: 'new',
      ai_summary: '',
      source: '',
      notes: '',
      icp_fit_score: null,
      embedding: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    expect(contact.name).toBe('Jane Smith')
  })
})
