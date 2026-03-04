// src/app/api/contacts/parse-linkedin/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { parseLinkedInPDF } from '@/lib/parsers/linkedin-pdf'

// POST /api/contacts/parse-linkedin
// Accepts: multipart/form-data with a "file" field containing a LinkedIn PDF
// Returns: extracted contact fields for user review — does NOT auto-create the contact
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get('file') as File | null

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 })
    }

    if (file.type !== 'application/pdf') {
      return NextResponse.json({ error: 'File must be a PDF' }, { status: 400 })
    }

    const buffer = Buffer.from(await file.arrayBuffer())
    const extracted = await parseLinkedInPDF(buffer)

    return NextResponse.json(extracted)
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to parse PDF'
    console.error('POST /api/contacts/parse-linkedin error:', err)
    return NextResponse.json({ error: message }, { status: 422 })
  }
}
