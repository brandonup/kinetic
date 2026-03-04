// src/lib/knowledge-processor.ts
import { YoutubeTranscript } from 'youtube-transcript'
import type { KnowledgeItem } from '@/types'

// --- URL Detection ---

export function isYouTubeUrl(url: string): boolean {
  if (!url) return false
  return /youtube\.com\/watch|youtu\.be\//.test(url)
}

export function extractYouTubeVideoId(url: string): string | null {
  const watchMatch = url.match(/[?&]v=([^&]+)/)
  if (watchMatch) return watchMatch[1]
  const shortMatch = url.match(/youtu\.be\/([^?&]+)/)
  if (shortMatch) return shortMatch[1]
  return null
}

// --- Content Fetching ---

export async function fetchYouTubeTranscript(videoId: string): Promise<string> {
  const transcript = await YoutubeTranscript.fetchTranscript(videoId)
  if (!transcript || transcript.length === 0) {
    throw new Error('No transcript available for this video')
  }
  // Strip timestamps, merge into clean paragraphs
  const rawText = transcript.map(t => t.text).join(' ')
  // Clean up whitespace and line breaks
  return rawText.replace(/\s+/g, ' ').trim()
}

export async function fetchUrlContent(url: string): Promise<{ title: string; content: string }> {
  const response = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; Kinetic/1.0)' },
  })
  if (!response.ok) throw new Error(`Failed to fetch URL: ${response.statusText}`)
  const html = await response.text()

  // Extract title
  const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i)
  const title = titleMatch ? titleMatch[1].trim() : url

  // Strip HTML tags and scripts
  const content = html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  return { title, content }
}

// --- Chunking ---

export function chunkText(text: string, chunkSize = 2000, overlap = 200): string[] {
  if (text.length <= chunkSize) return [text]

  const chunks: string[] = []
  let start = 0

  while (start < text.length) {
    const end = Math.min(start + chunkSize, text.length)
    chunks.push(text.slice(start, end))
    if (end === text.length) break
    start = end - overlap
  }

  return chunks
}

// --- Embedding Text Builder ---

export function buildKnowledgeEmbeddingText(item: {
  title: string
  ai_summary: string
  key_takeaways: string[]
}): string {
  return [
    item.title,
    item.ai_summary,
    item.key_takeaways.join(' | '),
  ]
    .filter(Boolean)
    .join('\n\n')
}

// Suppress unused import warning — KnowledgeItem is used for type context in downstream files
export type { KnowledgeItem }
