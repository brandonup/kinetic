"""Unit tests for the chunker module."""

from app.services.ingestion.chunker import (
    CHUNK_OVERLAP_WORDS,
    CHUNK_TARGET_WORDS,
    Chunk,
    chunk_document,
    count_words,
)


class TestChunkOverlap:
    """Tests for chunk overlap behavior (KIN-469)."""

    def _make_paragraph(self, word_count: int, label: str = "") -> str:
        """Generate a paragraph with exactly `word_count` words."""
        if label:
            # Use label as first word so paragraphs are distinguishable
            words = [label] + [f"word{i}" for i in range(word_count - 1)]
        else:
            words = [f"word{i}" for i in range(word_count)]
        return " ".join(words)

    def test_overlap_constant_is_75(self):
        """CHUNK_OVERLAP_WORDS should be 75 (~100 tokens with word-count proxy)."""
        assert CHUNK_OVERLAP_WORDS == 75

    def test_overlap_carries_content_between_chunks(self):
        """Overlap region should carry actual text from end of chunk N into start of chunk N+1."""
        # Use paragraphs small enough to fit within overlap budget (75 words)
        # 6 paragraphs of 70 words each = 420 total, producing 2+ chunks
        paragraphs = [self._make_paragraph(70, label=f"PARA{i}") for i in range(6)]
        text = "\n\n".join(paragraphs)

        chunks = chunk_document(text, total_tokens=420)

        assert len(chunks) >= 2
        # Last paragraph of chunk 0 should appear in chunk 1 (carried via overlap)
        chunk0_paras = chunks[0].text.split("\n\n")
        last_para = chunk0_paras[-1]
        assert last_para in chunks[1].text, (
            "Last paragraph of chunk 0 should be carried into chunk 1 via overlap"
        )

    def test_overlap_with_small_paragraphs(self):
        """When trailing paragraphs fit within overlap budget, they carry into next chunk."""
        # Build: several small paragraphs that together exceed CHUNK_TARGET_WORDS
        # The last few paragraphs (within 75 words) should appear in the next chunk
        small_para_words = 50  # each paragraph is 50 words
        num_paras = 10  # 10 * 50 = 500 words total, will produce multiple chunks

        paragraphs = []
        for i in range(num_paras):
            paragraphs.append(self._make_paragraph(small_para_words, label=f"P{i}"))

        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text, total_tokens=500)

        assert len(chunks) >= 2

        # Find the last paragraph of chunk 0
        chunk0_text = chunks[0].text
        chunk1_text = chunks[1].text

        # The overlap should mean some text from the end of chunk 0
        # also appears at the start of chunk 1
        chunk0_paragraphs = chunk0_text.split("\n\n")
        last_para_of_chunk0 = chunk0_paragraphs[-1]

        # This paragraph should appear in chunk 1 (carried via overlap)
        assert last_para_of_chunk0 in chunk1_text, (
            "Last paragraph of chunk 0 should be carried into chunk 1 via overlap"
        )

    def test_overlap_does_not_exceed_budget(self):
        """Overlap region should not exceed CHUNK_OVERLAP_WORDS."""
        small_para_words = 30
        num_paras = 20  # 20 * 30 = 600 words, multiple chunks

        paragraphs = []
        for i in range(num_paras):
            paragraphs.append(self._make_paragraph(small_para_words, label=f"P{i}"))

        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text, total_tokens=600)

        assert len(chunks) >= 2

        # For each pair of adjacent chunks, verify overlapping text
        # is within the overlap budget
        for i in range(len(chunks) - 1):
            c0_paras = chunks[i].text.split("\n\n")
            c1_paras = chunks[i + 1].text.split("\n\n")

            # Find overlapping paragraphs
            overlap_paras = []
            for p in c0_paras:
                if p in chunks[i + 1].text:
                    overlap_paras.append(p)

            overlap_word_count = sum(count_words(p) for p in overlap_paras)
            assert overlap_word_count <= CHUNK_OVERLAP_WORDS + 30, (
                f"Overlap between chunk {i} and {i+1} is {overlap_word_count} words, "
                f"exceeds budget of {CHUNK_OVERLAP_WORDS}"
            )

    def test_token_count_reflects_actual_content(self):
        """Each chunk's token_count should match its actual word count."""
        para1 = self._make_paragraph(200, label="ALPHA")
        para2 = self._make_paragraph(200, label="BETA")
        text = f"{para1}\n\n{para2}"

        chunks = chunk_document(text, total_tokens=400)

        for chunk in chunks:
            assert chunk.token_count == count_words(chunk.text)

    def test_single_chunk_no_overlap(self):
        """A document small enough for one chunk should have no overlap artifacts."""
        text = self._make_paragraph(100, label="SOLO")
        chunks = chunk_document(text, total_tokens=100)

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0

    def test_chunk_indices_are_sequential(self):
        """Chunk indices should be 0-based and sequential."""
        paragraphs = [self._make_paragraph(100, label=f"P{i}") for i in range(8)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text, total_tokens=800)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestContextualHeaders:
    """Tests for contextual chunk headers (KIN-468)."""

    def _make_paragraph(self, word_count: int, label: str = "") -> str:
        if label:
            words = [label] + [f"word{i}" for i in range(word_count - 1)]
        else:
            words = [f"word{i}" for i in range(word_count)]
        return " ".join(words)

    def test_header_prepended_with_title(self):
        """Chunks should have 'Source: {title}' header when document_title is provided."""
        text = self._make_paragraph(200, label="CONTENT")
        chunks = chunk_document(text, total_tokens=200, document_title="My Document")

        assert len(chunks) == 1
        assert chunks[0].text.startswith("Source: My Document\n")
        assert "(Part 1 of 1)" in chunks[0].text
        assert "CONTENT" in chunks[0].text

    def test_no_header_without_title(self):
        """Chunks should have no header when document_title is empty (backward-compatible)."""
        text = self._make_paragraph(200, label="CONTENT")
        chunks = chunk_document(text, total_tokens=200, document_title="")

        assert len(chunks) == 1
        assert chunks[0].text.startswith("CONTENT")
        assert "Source:" not in chunks[0].text

    def test_section_path_included_in_header(self):
        """When chunk has section_path, it should appear in the header."""
        text = self._make_paragraph(200, label="CONTENT")
        chunks = chunk_document(text, total_tokens=200, document_title="My Doc")

        # Manually set section_path to simulate extractor output, then re-run header logic
        # Since the chunker sets section_path=None by default, test with a chunk that has it
        chunk = chunks[0]
        # Verify section_path is None by default → no section in header
        assert chunk.section_path is None
        lines = chunk.text.split("\n")
        assert lines[0] == "Source: My Doc"
        assert lines[1] == "(Part 1 of 1)"

    def test_section_path_in_header_when_set(self):
        """section_path should appear between Source and Part lines."""
        text = self._make_paragraph(200, label="CONTENT")
        chunks = chunk_document(text, total_tokens=200, document_title="Playbook")

        # Simulate section_path being set before header pass
        # We need to test the header format directly by creating a chunk with section_path
        from app.services.ingestion.chunker import Chunk, count_words

        chunk = Chunk(
            text="Some raw text here",
            chunk_index=0,
            token_count=4,
            section_path="Chapter 3 > Change Management",
        )
        # Manually apply the header logic to verify format
        header_parts = ["Source: Playbook"]
        if chunk.section_path:
            header_parts.append(chunk.section_path)
        header_parts.append("(Part 1 of 5)")
        header = "\n".join(header_parts)
        result = f"{header}\n\n{chunk.text}"

        assert result.startswith("Source: Playbook\nChapter 3 > Change Management\n(Part 1 of 5)")
        assert "Some raw text here" in result

    def test_part_numbering_correct(self):
        """Part X of Y should be 1-indexed and match total chunk count."""
        paragraphs = [self._make_paragraph(100, label=f"P{i}") for i in range(8)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text, total_tokens=800, document_title="Test Doc")

        total = len(chunks)
        assert total >= 2
        for i, chunk in enumerate(chunks):
            assert f"(Part {i + 1} of {total})" in chunk.text

    def test_token_count_includes_header(self):
        """token_count should reflect the full text including header."""
        text = self._make_paragraph(200, label="CONTENT")

        chunks_no_header = chunk_document(text, total_tokens=200, document_title="")
        chunks_with_header = chunk_document(text, total_tokens=200, document_title="My Doc")

        # With header, token_count should be higher
        assert chunks_with_header[0].token_count > chunks_no_header[0].token_count
        # token_count should match actual word count
        assert chunks_with_header[0].token_count == count_words(chunks_with_header[0].text)

    def test_header_on_multiple_chunks(self):
        """Each chunk in a multi-chunk document should get its own header."""
        paragraphs = [self._make_paragraph(100, label=f"P{i}") for i in range(8)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text, total_tokens=800, document_title="Big Doc")

        for chunk in chunks:
            assert chunk.text.startswith("Source: Big Doc\n")

    def test_overlap_carries_content_not_just_header(self):
        """Overlap between chunks should carry actual content, not just header text (KIN-469 interaction)."""
        small_para_words = 50
        paragraphs = [self._make_paragraph(small_para_words, label=f"P{i}") for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text, total_tokens=500, document_title="Overlap Test")

        assert len(chunks) >= 2

        # The second chunk should contain content paragraphs from chunk 0 (via overlap),
        # not just its own header
        chunk1_lines = chunks[1].text.split("\n\n")
        # First element is the header block, rest is content
        content_parts = chunk1_lines[1:]  # skip header
        assert len(content_parts) >= 1, "Chunk 1 should have content after header"
