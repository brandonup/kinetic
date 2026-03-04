// src/lib/parsers/pdf-adapter.ts
// Thin wrapper so tests can vi.mock('./pdf-adapter') at import-resolution time,
// preventing the real CJS bundle from ever loading in the jsdom test environment.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const pdfParse = require('pdf-parse') as (
  buffer: Buffer
) => Promise<{ text: string; numpages: number }>

export default pdfParse
