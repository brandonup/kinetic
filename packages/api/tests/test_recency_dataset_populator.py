"""KIN-483 — tests for the title-pattern → document_id resolver.

Only the pure logic in `populate_recency_dataset.py` is unit-testable —
`load_documents` requires a live Supabase. The script is loaded via
importlib because it sits under `packages/api/evals/` rather than `app/`,
keeping it standalone.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "evals"
        / "kb_retrieval"
        / "populate_recency_dataset.py"
    )
    spec = importlib.util.spec_from_file_location("populate_recency_dataset", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _docs() -> list[dict]:
    # Newest first — mirrors what load_documents() returns
    return [
        {"id": "id-vibe-newest", "title": "the-vibe-coding-bible-how-to-build", "document_date": "2026-05-19"},
        {"id": "id-vibe-mid",    "title": "the-vibe-coding-bible-how-to-build-part-2", "document_date": "2026-03-01"},
        {"id": "id-vibe-oldest", "title": "the-vibe-coding-bible-how-to-build-original", "document_date": "2025-08-01"},
        {"id": "id-chatgpt",     "title": "chatgpt-build-my-side-hustlethe-complete", "document_date": "2025-06-15"},
        {"id": "id-rag",         "title": "rag-the-complete-guide-to-retrieval", "document_date": "2026-02-10"},
        {"id": "id-no-date",     "title": "agent-infrastructure-control-layer", "created_at": "2026-01-01"},
    ]


class TestMatchPattern:
    def test_substring_case_insensitive(self):
        m = _load_module()
        out = m.match_pattern(_docs(), "VIBE-CODING")
        assert {d["id"] for d in out} == {"id-vibe-newest", "id-vibe-mid", "id-vibe-oldest"}

    def test_no_match_returns_empty(self):
        m = _load_module()
        assert m.match_pattern(_docs(), "nonexistent-slug") == []

    def test_empty_pattern_returns_empty(self):
        m = _load_module()
        assert m.match_pattern(_docs(), "") == []


class TestPickFreshAndStale:
    def test_distinct_patterns(self):
        m = _load_module()
        fresh, stale = m.pick_fresh_and_stale(_docs(), "vibe-coding", "chatgpt-build")
        assert fresh == "id-vibe-newest"  # newest of vibe matches
        assert stale == "id-chatgpt"

    def test_same_pattern_picks_newest_and_oldest(self):
        m = _load_module()
        fresh, stale = m.pick_fresh_and_stale(_docs(), "vibe-coding", "vibe-coding")
        assert fresh == "id-vibe-newest"
        assert stale == "id-vibe-oldest"

    def test_same_pattern_single_match(self):
        m = _load_module()
        fresh, stale = m.pick_fresh_and_stale(_docs(), "rag-the-complete", "rag-the-complete")
        assert fresh == "id-rag"
        assert stale is None  # only one match → no stale pair

    def test_unmatched_fresh_returns_none(self):
        m = _load_module()
        fresh, stale = m.pick_fresh_and_stale(_docs(), "nonexistent", "chatgpt-build")
        assert fresh is None
        assert stale == "id-chatgpt"


class TestPopulateCase:
    def test_passthrough_for_comment_header(self):
        m = _load_module()
        header = {"_comment": "header"}
        assert m.populate_case(header, _docs()) == header

    def test_resolves_placeholders(self):
        m = _load_module()
        case = {
            "case_type": "recency",
            "query": "q",
            "fresh_doc_title_pattern": "vibe-coding",
            "stale_doc_title_pattern": "chatgpt-build",
            "should_retrieve": ["<fresh_doc_id_x>"],
            "should_not_retrieve": ["<stale_doc_id_x>"],
        }
        out = m.populate_case(case, _docs())
        assert out["should_retrieve"] == ["id-vibe-newest"]
        assert out["should_not_retrieve"] == ["id-chatgpt"]
        assert out["_resolved_fresh_doc_id"] == "id-vibe-newest"
        assert out["_resolved_stale_doc_id"] == "id-chatgpt"

    def test_unresolved_placeholder_preserved(self):
        m = _load_module()
        case = {
            "case_type": "recency",
            "fresh_doc_title_pattern": "nonexistent",
            "stale_doc_title_pattern": "chatgpt-build",
            "should_retrieve": ["<fresh_doc_id_x>"],
            "should_not_retrieve": ["<stale_doc_id_x>"],
        }
        out = m.populate_case(case, _docs())
        assert out["should_retrieve"] == ["<fresh_doc_id_x>"]  # left as placeholder
        assert out["should_not_retrieve"] == ["id-chatgpt"]

    def test_non_placeholder_values_unchanged(self):
        """Real UUIDs already in the input pass through untouched."""
        m = _load_module()
        case = {
            "case_type": "recency",
            "fresh_doc_title_pattern": "vibe-coding",
            "stale_doc_title_pattern": "chatgpt-build",
            "should_retrieve": ["real-uuid-1234"],
            "should_not_retrieve": ["real-uuid-5678"],
        }
        out = m.populate_case(case, _docs())
        assert out["should_retrieve"] == ["real-uuid-1234"]
        assert out["should_not_retrieve"] == ["real-uuid-5678"]
