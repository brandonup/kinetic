"""
Fixed-size word-based chunker.

Target: ~375 words per chunk (~500 tokens), ~75 word overlap (~100 tokens).
Tokenizer: local word-count approximation (~1.33 tokens/word).

KIN-467: replaced tiktoken cl100k_base with word-count proxy to avoid
dependency on OpenAI's tokenizer. Gemini uses SentencePiece — no local
tokenizer available, and the API count_tokens() call is too slow for
the chunker loop (dozens of calls per document).

Strategy:
  1. Split on double-newline paragraph boundaries.
  2. Accumulate paragraphs into a buffer until CHUNK_TARGET_WORDS is reached.
  3. Flush: carry the last N paragraphs (up to CHUNK_OVERLAP_WORDS) into the next chunk.
  4. Single paragraphs that exceed CHUNK_TARGET_WORDS are split by sentence.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

CHUNK_TARGET_WORDS: int = 375     # ~500 tokens
CHUNK_OVERLAP_WORDS: int = 75     # ~100 tokens — preserves concluding thought across chunk boundaries for prose/transcript content


@dataclass
class Chunk:
    text: str
    chunk_index: int
    token_count: int  # word count (proxy for tokens)
    section_path: Optional[str] = None
    page_range: Optional[str] = None


def count_words(text: str) -> int:
    """Count words in text. Used as token-count proxy (~1.33 tokens/word)."""
    return len(text.split())


def _split_sentences(text: str) -> List[str]:
    """Split text on sentence boundaries."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _split_large_paragraph(para: str, target: int) -> List[str]:
    """Split a single paragraph that exceeds target words into sentence-based sub-chunks."""
    sentences = _split_sentences(para)
    sub_chunks: List[str] = []
    buffer: List[str] = []
    buf_words = 0

    for sentence in sentences:
        w = count_words(sentence)
        if buffer and buf_words + w > target:
            sub_chunks.append(" ".join(buffer))
            buffer = []
            buf_words = 0
        buffer.append(sentence)
        buf_words += w

    if buffer:
        sub_chunks.append(" ".join(buffer))

    return sub_chunks


def chunk_document(
    text: str, total_tokens: int, document_title: str = "",
) -> List[Chunk]:
    """
    Split document text into fixed-size chunks with overlap.

    Args:
        text: Full extracted document text.
        total_tokens: Pre-computed token count (used for logging only).
        document_title: Document title for contextual chunk headers.
            When provided, each chunk gets a header prepended before embedding:
            "Source: {title}\\n{section_path}\\n(Part X of Y)\\n\\n{text}"

    Returns:
        List of Chunk objects ordered by chunk_index.
    """
    # Split into paragraphs; further split any oversized paragraphs.
    raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    paragraphs: List[str] = []
    for para in raw_paragraphs:
        w = count_words(para)
        if w > CHUNK_TARGET_WORDS:
            paragraphs.extend(_split_large_paragraph(para, CHUNK_TARGET_WORDS))
        else:
            paragraphs.append(para)

    if not paragraphs:
        logger.warning("No paragraphs extracted from document; returning single empty chunk")
        return [Chunk(text=text[:2000], chunk_index=0, token_count=min(total_tokens, 2000))]

    chunks: List[Chunk] = []
    buffer: List[str] = []
    buf_words = 0
    idx = 0

    def _flush() -> Chunk:
        joined = "\n\n".join(buffer)
        return Chunk(
            text=joined,
            chunk_index=idx,
            token_count=count_words(joined),
        )

    for para in paragraphs:
        para_words = count_words(para)

        if buffer and buf_words + para_words > CHUNK_TARGET_WORDS:
            chunks.append(_flush())
            idx += 1

            # Build overlap: keep last paragraphs up to CHUNK_OVERLAP_WORDS
            overlap: List[str] = []
            overlap_words = 0
            for prev in reversed(buffer):
                w = count_words(prev)
                if overlap_words + w > CHUNK_OVERLAP_WORDS:
                    break
                overlap.insert(0, prev)
                overlap_words += w

            buffer = overlap
            buf_words = overlap_words

        buffer.append(para)
        buf_words += para_words

    if buffer:
        chunks.append(_flush())

    # Second pass: prepend contextual headers (KIN-468).
    # Requires total chunk count, so must run after first pass completes.
    if document_title:
        for i, chunk in enumerate(chunks):
            header_parts = [f"Source: {document_title}"]
            if chunk.section_path:
                header_parts.append(chunk.section_path)
            header_parts.append(f"(Part {i + 1} of {len(chunks)})")
            header = "\n".join(header_parts)
            chunk.text = f"{header}\n\n{chunk.text}"
            chunk.token_count = count_words(chunk.text)

    logger.info("Chunked document into %d chunks (total_tokens=%d)", len(chunks), total_tokens)
    return chunks
