// src/lib/openai.ts
import OpenAI from 'openai'

// Lazy singleton — env check deferred to first call so Next.js build doesn't throw at module eval
let _client: OpenAI | null = null

export const openaiClient = new Proxy({} as OpenAI, {
  get(_target, prop) {
    if (!_client) {
      if (!process.env.OPENAI_API_KEY) throw new Error('Missing OPENAI_API_KEY')
      _client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const value = (_client as any)[prop]
    return typeof value === 'function' ? value.bind(_client) : value
  },
})
