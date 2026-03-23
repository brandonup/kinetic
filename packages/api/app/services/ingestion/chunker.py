"""
Fixed-size token-based chunker.

Target: ~500 tokens per chunk, ~50 token overlap.
Encoding: cl100k_base (tiktoken) — same encoder used by text-embedding-3-large.

Strategy:
  1. Split on double-newline paragraph boundaries.
  2. Accumulate paragraphs into a buffer until CHUNK_TARGET_TOKENS is reached.
  3. Flush: carry the last N paragraphs (up to CHUNK_OVERLAP_TOKENS) into the next chunk.
  4. Single paragraphs that exceed CHUNK_TARGET_TOKENS are split by sentence.

V1 enhancements (semantic chunking, per-chunk enrichment) are config-flag stubs —
implement chunker.py swap when SEMANTIC_CHUNKING_ENABLED is true.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import tiktoken

logger = logging.getLogger(__name__)

CHUNK_TARGET_TOKENS: int = 500
CHUNK_OVERLAP_TOKENS: int = 50
_ENCODING_NAME: str = "cl100k_base"


@dataclass
class Chunk:
    text: str
    chunk_index: int
    token_count: int
    section_path: Optional[str] = None
    page_range: Optional[str] = None


def _get_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base encoding."""
    return len(_get_encoding().encode(text))


def _split_sentences(text: str) -> List[str]:
    """Split text on sentence boundaries."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _split_large_paragraph(para: str, target: int) -> List[str]:
    """Split a single paragraph that exceeds target tokens into sentence-based sub-chunks."""
    enc = _get_encoding()
    sentences = _split_sentences(para)
    sub_chunks: List[str] = []
    buffer: List[str] = []
    buf_tokens = 0

    for sentence in sentences:
        t = len(enc.encode(sentence))
        if buffer and buf_tokens + t > target:
            sub_chunks.append(" ".join(buffer))
            buffer = []
            buf_tokens = 0
        buffer.append(sentence)
        buf_tokens += t

    if buffer:
        sub_chunks.append(" ".join(buffer))

    return sub_chunks


def chunk_document(text: str, total_tokens: int) -> List[Chunk]:
    """
    Split document text into fixed-size chunks with overlap.

    Args:
        text: Full extracted document text.
        total_tokens: Pre-computed token count (used for logging only).

    Returns:
        List of Chunk objects ordered by chunk_index.
    """
    enc = _get_encoding()

    # Split into paragraphs; further split any oversized paragraphs.
    raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    paragraphs: List[str] = []
    for para in raw_paragraphs:
        t = len(enc.encode(para))
        if t > CHUNK_TARGET_TOKENS:
            paragraphs.extend(_split_large_paragraph(para, CHUNK_TARGET_TOKENS))
        else:
            paragraphs.append(para)

    if not paragraphs:
        logger.warning("No paragraphs extracted from document; returning single empty chunk")
        return [Chunk(text=text[:2000], chunk_index=0, token_count=min(total_tokens, 2000))]

    chunks: List[Chunk] = []
    buffer: List[str] = []
    buf_tokens = 0
    idx = 0

    def _flush() -> Chunk:
        joined = "\n\n".join(buffer)
        return Chunk(
            text=joined,
            chunk_index=idx,
            token_count=len(enc.encode(joined)),
        )

    for para in paragraphs:
        para_tokens = len(enc.encode(para))

        if buffer and buf_tokens + para_tokens > CHUNK_TARGET_TOKENS:
            chunks.append(_flush())
            idx += 1

            # Build overlap: keep last paragraphs up to CHUNK_OVERLAP_TOKENS
            overlap: List[str] = []
            overlap_tokens = 0
            for prev in reversed(buffer):
                t = len(enc.encode(prev))
                if overlap_tokens + t > CHUNK_OVERLAP_TOKENS:
                    break
                overlap.insert(0, prev)
                overlap_tokens += t

            buffer = overlap
            buf_tokens = overlap_tokens

        buffer.append(para)
        buf_tokens += para_tokens

    if buffer:
        chunks.append(_flush())

    logger.info("Chunked document into %d chunks (total_tokens=%d)", len(chunks), total_tokens)
    return chunks
