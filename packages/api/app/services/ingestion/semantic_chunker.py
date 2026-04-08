"""
Semantic chunker using sliding-window topic segmentation.

Detects topic boundaries via embedding cosine similarity between
adjacent text windows. Forms variable-size chunks that follow the
natural structure of the content rather than arbitrary token limits.

Designed for podcast/lecture transcripts and long-form articles where
fixed-size splitting cuts through the middle of arguments and ideas.

KIN-470: Uses Gemini Embedding 001 via platform key (KIN-467).
Supports contextual headers (KIN-468).
"""

from __future__ import annotations

import logging
import math
import statistics
from typing import List, Optional

from app.core.config import settings
from app.services.ingestion.chunker import (
    Chunk,
    _split_sentences,
    chunk_document,
    count_words,
)
from app.services.ingestion.embedder import EmbeddingService

logger = logging.getLogger(__name__)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _form_windows(
    sentences: List[str], window_words: int, stride: int = 1,
) -> tuple[List[str], List[int]]:
    """
    Form overlapping windows of approximately `window_words` words.

    Each window is a contiguous group of sentences starting at every
    `stride`-th sentence. Returns both the window texts and the starting
    sentence index for each window (needed for breakpoint-to-sentence mapping).

    Args:
        sentences: List of individual sentences.
        window_words: Target word count per window.
        stride: Number of sentences to advance between windows. Higher stride
            reduces embedding cost at the expense of boundary resolution.

    Returns:
        Tuple of (window_texts, window_start_indices).
    """
    windows: List[str] = []
    start_indices: List[int] = []
    for start in range(0, len(sentences), stride):
        buf: List[str] = []
        word_count = 0
        for i in range(start, len(sentences)):
            s_words = count_words(sentences[i])
            if buf and word_count + s_words > window_words * 1.5:
                break
            buf.append(sentences[i])
            word_count += s_words
            if word_count >= window_words:
                break
        if buf:
            windows.append(" ".join(buf))
            start_indices.append(start)
    return windows, start_indices


def _detect_breakpoints(
    similarities: List[float], threshold_multiplier: float,
) -> List[int]:
    """
    Detect topic breakpoints where similarity drops significantly.

    Returns indices into the similarities list where breaks occur.
    A breakpoint at index i means there's a topic shift between
    window i and window i+1.
    """
    if len(similarities) < 3:
        return []

    mean = statistics.mean(similarities)
    stdev = statistics.stdev(similarities) if len(similarities) > 1 else 0.0

    if stdev == 0.0:
        return []

    threshold = mean - threshold_multiplier * stdev
    return [i for i, sim in enumerate(similarities) if sim < threshold]


def _merge_small_chunks(
    chunks: List[List[str]], min_words: int,
) -> List[List[str]]:
    """Merge chunks smaller than min_words with their nearest neighbor."""
    if not chunks:
        return chunks

    merged: List[List[str]] = [chunks[0]]
    for chunk_sentences in chunks[1:]:
        chunk_words = sum(count_words(s) for s in chunk_sentences)
        prev_words = sum(count_words(s) for s in merged[-1])

        if chunk_words < min_words or prev_words < min_words:
            merged[-1].extend(chunk_sentences)
        else:
            merged.append(chunk_sentences)

    # Final pass: if last chunk is too small, merge with previous
    if len(merged) > 1:
        last_words = sum(count_words(s) for s in merged[-1])
        if last_words < min_words:
            merged[-2].extend(merged.pop())

    return merged


def _split_large_chunks(
    chunks: List[List[str]], max_words: int,
) -> List[List[str]]:
    """Split chunks larger than max_words at sentence boundaries."""
    result: List[List[str]] = []
    for chunk_sentences in chunks:
        total_words = sum(count_words(s) for s in chunk_sentences)
        if total_words <= max_words:
            result.append(chunk_sentences)
            continue

        current: List[str] = []
        current_words = 0
        for sentence in chunk_sentences:
            s_words = count_words(sentence)
            if current and current_words + s_words > max_words:
                result.append(current)
                current = []
                current_words = 0
            current.append(sentence)
            current_words += s_words
        if current:
            result.append(current)

    return result


def chunk_document_semantic(
    text: str,
    total_tokens: int,
    document_title: str = "",
) -> List[Chunk]:
    """
    Split document text into topic-coherent chunks using embedding similarity.

    Falls back to fixed-size chunker if the document is too short for
    meaningful topic detection (< 5 sentences or < 3 windows).

    Args:
        text: Full extracted document text.
        total_tokens: Pre-computed token count (used for logging only).
        document_title: Document title for contextual chunk headers (KIN-468).

    Returns:
        List of Chunk objects ordered by chunk_index.
    """
    sentences = _split_sentences(text)

    if len(sentences) < 5:
        logger.info(
            "Document too short for semantic chunking (%d sentences), "
            "falling back to fixed-size",
            len(sentences),
        )
        return chunk_document(text, total_tokens, document_title=document_title)

    # Step 1: Form sliding windows with configurable stride.
    # Stride > 1 reduces the number of embedding API calls at the cost of
    # slightly coarser boundary detection. Default stride=3 gives ~1/3 the
    # windows vs stride=1.
    windows, window_starts = _form_windows(
        sentences, settings.SEMANTIC_WINDOW_WORDS,
        stride=settings.SEMANTIC_WINDOW_STRIDE,
    )

    if len(windows) < 3:
        logger.info(
            "Too few windows for semantic chunking (%d), falling back to fixed-size",
            len(windows),
        )
        return chunk_document(text, total_tokens, document_title=document_title)

    # Step 2: Embed all windows for topic boundary detection.
    # NOTE: This is a separate embedding pass for boundary detection only —
    # the actual chunk embeddings happen later in the pipeline's embedding stage.
    # Errors here surface as "chunking" stage failures in the retry logic.
    logger.info(
        "Embedding %d windows for topic boundary detection (stride=%d, "
        "sentences=%d)",
        len(windows), settings.SEMANTIC_WINDOW_STRIDE, len(sentences),
    )
    embedder = EmbeddingService()
    window_embeddings = embedder.embed_batch(windows)

    # Step 3: Compute cosine similarity between adjacent windows
    similarities: List[float] = []
    for i in range(len(window_embeddings) - 1):
        sim = _cosine_similarity(window_embeddings[i], window_embeddings[i + 1])
        similarities.append(sim)

    # Step 4: Detect breakpoints
    breakpoints = _detect_breakpoints(
        similarities, settings.SEMANTIC_BREAKPOINT_THRESHOLD,
    )

    # Step 5: Form chunks between breakpoints.
    # Breakpoint at similarity index i means a topic shift between window i
    # and window i+1. Map back to sentence indices using window_starts.
    # The break happens after the last sentence of window i's starting position.
    break_sentence_indices = set()
    for bp in breakpoints:
        # The sentence where the break occurs is the start of the *next* window
        if bp + 1 < len(window_starts):
            break_sentence_indices.add(window_starts[bp + 1] - 1)

    chunk_groups: List[List[str]] = []
    current_group: List[str] = []

    for i, sentence in enumerate(sentences):
        current_group.append(sentence)
        if i in break_sentence_indices and current_group:
            chunk_groups.append(current_group)
            current_group = []

    if current_group:
        chunk_groups.append(current_group)

    # Step 6: Merge small chunks, split large chunks
    chunk_groups = _merge_small_chunks(chunk_groups, settings.SEMANTIC_MIN_CHUNK_WORDS)
    chunk_groups = _split_large_chunks(chunk_groups, settings.SEMANTIC_MAX_CHUNK_WORDS)

    # Step 7: Build Chunk objects
    chunks: List[Chunk] = []
    for idx, group in enumerate(chunk_groups):
        joined = " ".join(group)
        chunks.append(Chunk(
            text=joined,
            chunk_index=idx,
            token_count=count_words(joined),
        ))

    # Step 8: Prepend contextual headers (KIN-468)
    if document_title:
        for i, chunk in enumerate(chunks):
            header_parts = [f"Source: {document_title}"]
            if chunk.section_path:
                header_parts.append(chunk.section_path)
            header_parts.append(f"(Part {i + 1} of {len(chunks)})")
            header = "\n".join(header_parts)
            chunk.text = f"{header}\n\n{chunk.text}"
            chunk.token_count = count_words(chunk.text)

    logger.info(
        "Semantic chunking: %d chunks from %d sentences, %d breakpoints, "
        "%d windows (total_tokens=%d)",
        len(chunks), len(sentences), len(breakpoints), len(windows), total_tokens,
    )
    return chunks
