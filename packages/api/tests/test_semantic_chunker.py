"""Unit tests for semantic chunker (KIN-470)."""

import math
from unittest.mock import MagicMock, patch
from typing import List

import pytest

from app.core.config import settings
from app.services.ingestion.chunker import Chunk, _split_sentences, count_words
from app.services.ingestion.semantic_chunker import (
    _cosine_similarity,
    _detect_breakpoints,
    _form_windows,
    _merge_small_chunks,
    _split_large_chunks,
    chunk_document_semantic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_topic_text(topic_word: str, sentence_count: int = 10) -> str:
    """Generate sentences about a single 'topic' using a repeated keyword."""
    sentences = []
    for i in range(sentence_count):
        sentences.append(
            f"The {topic_word} aspect is important for understanding point {i}. "
            f"Experts agree that {topic_word} drives outcomes in this area."
        )
    return " ".join(sentences)


def _make_two_topic_text() -> str:
    """Two clearly distinct topics separated by many sentences."""
    topic_a = _make_topic_text("artificial_intelligence", 15)
    topic_b = _make_topic_text("marine_biology", 15)
    return f"{topic_a} {topic_b}"


def _mock_embeddings_with_topic_shift(n_windows: int, break_at: int) -> List[List[float]]:
    """
    Create mock embeddings where windows before break_at are similar
    (topic A) and windows after are similar (topic B).
    """
    dim = settings.EMBEDDING_DIMS
    vec_a = [0.0] * dim
    vec_a[0] = 1.0
    vec_b = [0.0] * dim
    vec_b[1] = 1.0

    embeddings = []
    for i in range(n_windows):
        if i < break_at:
            vec = vec_a.copy()
            vec[2] = 0.01 * (i + 1)
            norm = math.sqrt(sum(x * x for x in vec))
            embeddings.append([x / norm for x in vec])
        else:
            vec = vec_b.copy()
            vec[3] = 0.01 * (i + 1)
            norm = math.sqrt(sum(x * x for x in vec))
            embeddings.append([x / norm for x in vec])
    return embeddings


# ---------------------------------------------------------------------------
# Unit tests: internal functions
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_basic_split(self):
        text = "Hello world. How are you? I'm fine!"
        assert _split_sentences(text) == ["Hello world.", "How are you?", "I'm fine!"]

    def test_no_split(self):
        assert _split_sentences("Single sentence") == ["Single sentence"]


class TestFormWindows:
    def test_creates_windows_with_stride(self):
        sentences = [f"Sentence number {i} with some words." for i in range(10)]
        windows, starts = _form_windows(sentences, window_words=20, stride=1)
        assert len(windows) >= 5
        assert len(starts) == len(windows)
        assert starts[0] == 0

    def test_stride_reduces_window_count(self):
        sentences = [f"Sentence number {i} with some words." for i in range(20)]
        w1, _ = _form_windows(sentences, window_words=20, stride=1)
        w3, _ = _form_windows(sentences, window_words=20, stride=3)
        assert len(w3) < len(w1)

    def test_start_indices_respect_stride(self):
        sentences = [f"Sentence {i} here." for i in range(12)]
        _, starts = _form_windows(sentences, window_words=20, stride=3)
        for i in range(len(starts)):
            assert starts[i] % 3 == 0


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


class TestDetectBreakpoints:
    def test_uniform_similarities_no_breakpoints(self):
        sims = [0.95, 0.94, 0.96, 0.95, 0.94]
        breaks = _detect_breakpoints(sims, 1.5)
        assert len(breaks) == 0

    def test_one_clear_drop(self):
        sims = [0.95, 0.94, 0.96, 0.10, 0.95, 0.94]
        breaks = _detect_breakpoints(sims, 1.5)
        assert 3 in breaks

    def test_too_few_similarities(self):
        assert _detect_breakpoints([0.5], 1.5) == []
        assert _detect_breakpoints([0.5, 0.5], 1.5) == []


class TestMergeSmallChunks:
    def test_merges_tiny_chunks(self):
        chunks = [
            ["Word " * 20 + "."],
            ["Tiny."],
            ["Word " * 20 + "."],
        ]
        merged = _merge_small_chunks(chunks, min_words=10)
        assert len(merged) < 3

    def test_keeps_large_chunks(self):
        chunks = [
            [f"Word{i} " * 50 + "." for i in range(3)],
            [f"Word{i} " * 50 + "." for i in range(3)],
        ]
        merged = _merge_small_chunks(chunks, min_words=10)
        assert len(merged) == 2


class TestSplitLargeChunks:
    def test_splits_oversized_chunk(self):
        big = [f"This is sentence number {i} with some extra words here." for i in range(30)]
        result = _split_large_chunks([big], max_words=100)
        assert len(result) > 1
        for group in result:
            words = sum(count_words(s) for s in group)
            assert words <= 150

    def test_keeps_small_chunk(self):
        small = ["Short sentence."]
        result = _split_large_chunks([small], max_words=100)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration tests: chunk_document_semantic
# ---------------------------------------------------------------------------

class TestChunkDocumentSemantic:
    """Tests for the full semantic chunking pipeline with mocked embeddings."""

    def _get_window_count(self, text):
        """Helper: get window count for mock embedding sizing."""
        sentences = _split_sentences(text)
        windows, _ = _form_windows(sentences, 112, stride=3)
        return len(windows)

    @patch("app.services.ingestion.semantic_chunker.EmbeddingService")
    def test_two_topics_produce_multiple_chunks(self, MockEmbedder):
        """Two distinct topics should produce at least 2 chunks."""
        text = _make_two_topic_text()
        n_windows = self._get_window_count(text)

        mock_instance = MagicMock()
        mock_embeddings = _mock_embeddings_with_topic_shift(
            n_windows, break_at=n_windows // 2,
        )
        mock_instance.embed_batch.return_value = mock_embeddings
        MockEmbedder.return_value = mock_instance

        chunks = chunk_document_semantic(text, total_tokens=500)

        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.chunk_index == i for i, c in enumerate(chunks))

    @patch("app.services.ingestion.semantic_chunker.EmbeddingService")
    def test_single_topic_single_chunk(self, MockEmbedder):
        """A coherent single-topic text should produce 1 chunk (if within max size)."""
        text = _make_topic_text("blockchain", 10)
        n_windows = self._get_window_count(text)

        dim = settings.EMBEDDING_DIMS
        base_vec = [0.0] * dim
        base_vec[0] = 1.0
        mock_embeddings = [base_vec[:] for _ in range(n_windows)]
        mock_instance = MagicMock()
        mock_instance.embed_batch.return_value = mock_embeddings
        MockEmbedder.return_value = mock_instance

        chunks = chunk_document_semantic(text, total_tokens=200)

        assert len(chunks) == 1

    @patch("app.services.ingestion.semantic_chunker.EmbeddingService")
    def test_contextual_headers_applied(self, MockEmbedder):
        """document_title should produce headers on each chunk."""
        text = _make_two_topic_text()
        n_windows = self._get_window_count(text)

        mock_instance = MagicMock()
        mock_embeddings = _mock_embeddings_with_topic_shift(
            n_windows, break_at=n_windows // 2,
        )
        mock_instance.embed_batch.return_value = mock_embeddings
        MockEmbedder.return_value = mock_instance

        chunks = chunk_document_semantic(
            text, total_tokens=500, document_title="Test Document",
        )

        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.text.startswith("Source: Test Document\n")

    @patch("app.services.ingestion.semantic_chunker.EmbeddingService")
    def test_no_header_without_title(self, MockEmbedder):
        """Empty document_title means no header."""
        text = _make_two_topic_text()
        n_windows = self._get_window_count(text)

        mock_instance = MagicMock()
        mock_embeddings = _mock_embeddings_with_topic_shift(
            n_windows, break_at=n_windows // 2,
        )
        mock_instance.embed_batch.return_value = mock_embeddings
        MockEmbedder.return_value = mock_instance

        chunks = chunk_document_semantic(text, total_tokens=500, document_title="")

        for chunk in chunks:
            assert "Source:" not in chunk.text

    @patch("app.services.ingestion.semantic_chunker.EmbeddingService")
    def test_token_count_matches_word_count(self, MockEmbedder):
        """Each chunk's token_count should equal its word count."""
        text = _make_two_topic_text()
        n_windows = self._get_window_count(text)

        mock_instance = MagicMock()
        mock_embeddings = _mock_embeddings_with_topic_shift(
            n_windows, break_at=n_windows // 2,
        )
        mock_instance.embed_batch.return_value = mock_embeddings
        MockEmbedder.return_value = mock_instance

        chunks = chunk_document_semantic(
            text, total_tokens=500, document_title="Doc",
        )

        for chunk in chunks:
            assert chunk.token_count == count_words(chunk.text)

    def test_short_text_falls_back(self):
        """Very short text (< 5 sentences) should fall back to fixed-size chunker."""
        text = "Short text. Only two sentences."
        with patch(
            "app.services.ingestion.semantic_chunker.chunk_document",
        ) as mock_fixed:
            mock_fixed.return_value = [
                Chunk(text=text, chunk_index=0, token_count=5),
            ]
            chunks = chunk_document_semantic(text, total_tokens=5)
            mock_fixed.assert_called_once()
            assert len(chunks) == 1

    @patch("app.services.ingestion.semantic_chunker.EmbeddingService")
    def test_chunks_respect_min_size(self, MockEmbedder):
        """Chunks should be at least 100 words after merge logic."""
        text = _make_two_topic_text()
        n_windows = self._get_window_count(text)

        mock_instance = MagicMock()
        mock_embeddings = _mock_embeddings_with_topic_shift(
            n_windows, break_at=n_windows // 2,
        )
        mock_instance.embed_batch.return_value = mock_embeddings
        MockEmbedder.return_value = mock_instance

        chunks = chunk_document_semantic(text, total_tokens=500)

        for chunk in chunks:
            assert chunk.token_count >= 100, (
                f"Chunk {chunk.chunk_index} too small: {chunk.token_count} words"
            )
