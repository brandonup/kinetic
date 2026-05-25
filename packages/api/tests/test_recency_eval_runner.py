"""
Self-tests for the recency eval runner (KIN-492).

These verify the runner's assertion logic, aggregation, and byte-identical
regression mode using fake retrieved-chunk objects and synthetic cases —
no live Supabase calls. They are the proof that the runner itself works
when Brandon turns it on against the real Nate KB.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

import pytest

# Make `evals.*` importable for tests (KIN-449 runner already lives there).
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), ".."),
)

from evals.kb_retrieval.recency_eval_runner import (  # noqa: E402
    _collect_off_state_signature,
    _contains_staleness_flag,
    _doc_ranks,
    _result_stub,
    aggregate_results,
    compare_signatures,
    evaluate_contradiction_case,
    evaluate_control_case,
    evaluate_over_flagging_case,
    evaluate_recency_case,
    is_dataset_populated,
    load_dataset,
)


# ---------------------------------------------------------------------------
# Fake RetrievedChunk — the runner only reads chunk_id, document_id,
# similarity_score, so we don't need a full dataclass.
# ---------------------------------------------------------------------------


@dataclass
class FakeChunk:
    chunk_id: str
    document_id: str
    similarity_score: float


def chunk(doc_id: str, *, score: float = 0.7, chunk_id: str | None = None) -> FakeChunk:
    return FakeChunk(
        chunk_id=chunk_id or f"chk-{doc_id}-1",
        document_id=doc_id,
        similarity_score=score,
    )


# ---------------------------------------------------------------------------
# Dataset loading + placeholder detection
# ---------------------------------------------------------------------------


class TestDatasetLoading:
    def test_load_dataset_drops_comment_only_lines(self, tmp_path):
        path = tmp_path / "ds.jsonl"
        path.write_text(
            '{"_comment": "header comment"}\n'
            '{"case_type": "recency", "query": "Q1"}\n'
            "\n"
            '{"case_type": "control", "query": "Q2"}\n'
        )
        cases = load_dataset(str(path))
        assert [c["query"] for c in cases] == ["Q1", "Q2"]

    def test_is_dataset_populated_flags_template_placeholders(self):
        template_case = {
            "case_type": "recency",
            "query": "q",
            "should_retrieve": ["<fresh_doc_id_1>"],
            "should_not_retrieve": ["<stale_doc_id_1>"],
        }
        populated, offending = is_dataset_populated([template_case])
        assert populated is False
        assert "<fresh_doc_id_1>" in offending
        assert "<stale_doc_id_1>" in offending

    def test_is_dataset_populated_accepts_real_uuids(self):
        real_case = {
            "case_type": "recency",
            "query": "q",
            "should_retrieve": ["11111111-1111-1111-1111-111111111111"],
            "should_not_retrieve": ["22222222-2222-2222-2222-222222222222"],
        }
        populated, offending = is_dataset_populated([real_case])
        assert populated is True
        assert offending == []

    def test_is_dataset_populated_handles_empty_lists(self):
        # Control cases legitimately have empty should/should_not — must not
        # trip the placeholder check.
        control = {
            "case_type": "control",
            "query": "q",
            "should_retrieve": [],
            "should_not_retrieve": [],
        }
        populated, _ = is_dataset_populated([control])
        assert populated is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestDocRanks:
    def test_first_occurrence_wins(self):
        # When a doc has two chunks in the result, the rank is the first.
        chunks = [chunk("A"), chunk("B"), chunk("A"), chunk("C")]
        assert _doc_ranks(chunks) == {"A": 1, "B": 2, "C": 4}

    def test_empty_chunk_list(self):
        assert _doc_ranks([]) == {}


# ---------------------------------------------------------------------------
# Recency-case assertions
# ---------------------------------------------------------------------------


class TestEvaluateRecencyCase:
    def _case(self, fresh: str, stale: str | None) -> dict:
        return {
            "case_type": "recency",
            "query": "q",
            "should_retrieve": [fresh],
            "should_not_retrieve": [stale] if stale else [],
        }

    def test_pass_when_fresh_above_stale(self):
        result = evaluate_recency_case(
            self._case("FRESH", "STALE"),
            [chunk("FRESH"), chunk("STALE")],
        )
        assert result["status"] == "PASS"
        assert result["fresh_rank"] == 1
        assert result["stale_rank"] == 2

    def test_fail_when_stale_above_fresh(self):
        result = evaluate_recency_case(
            self._case("FRESH", "STALE"),
            [chunk("STALE"), chunk("FRESH")],
        )
        assert result["status"] == "FAIL"
        assert "stale doc ranks above fresh" in result["reason"]

    def test_fail_when_fresh_missing(self):
        result = evaluate_recency_case(
            self._case("FRESH", "STALE"),
            [chunk("STALE"), chunk("OTHER")],
        )
        assert result["status"] == "FAIL"
        assert "fresh doc not retrieved" in result["reason"]

    def test_pass_when_stale_missing_no_comparison_needed(self):
        # Recency feature did its job — demoted the stale right off the list.
        result = evaluate_recency_case(
            self._case("FRESH", "STALE"),
            [chunk("FRESH"), chunk("OTHER")],
        )
        assert result["status"] == "PASS"
        assert "stale doc not retrieved" in result["reason"]

    def test_single_doc_probe_pass_when_fresh_retrieved(self):
        # The dataset has one case with no stale near-duplicate.
        result = evaluate_recency_case(
            self._case("FRESH", None),
            [chunk("FRESH"), chunk("OTHER")],
        )
        assert result["status"] == "PASS"

    def test_single_doc_probe_fail_when_fresh_not_retrieved(self):
        result = evaluate_recency_case(
            self._case("FRESH", None),
            [chunk("OTHER")],
        )
        assert result["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Contradiction-case assertions — generation gated by KIN-485
# ---------------------------------------------------------------------------


class TestEvaluateContradictionCase:
    def test_pass_when_answer_matches_pattern(self, monkeypatch):
        import evals.kb_retrieval.recency_eval_runner as runner

        monkeypatch.setattr(
            runner, "_generate_answer",
            lambda case, chunks: "No, that approach hasn't changed recently.",
        )
        case = {
            "case_type": "contradiction",
            "query": "q",
            "should_retrieve": ["FRESH", "STALE"],
            "should_not_retrieve": [],
            "expected_answer_pattern": r"no|hasn't changed",
            "expected_prefers_recent": True,
        }
        result = evaluate_contradiction_case(case, [chunk("FRESH"), chunk("STALE")])
        assert result["status"] == "PASS"
        # Retrieval coverage still reported even on pass.
        assert result["retrieval_coverage"] == 1.0
        assert "answer" in result

    def test_fail_when_answer_does_not_match_pattern(self, monkeypatch):
        import evals.kb_retrieval.recency_eval_runner as runner

        monkeypatch.setattr(
            runner, "_generate_answer",
            lambda case, chunks: "Yes, everything has completely changed.",
        )
        case = {
            "case_type": "contradiction",
            "query": "q",
            "should_retrieve": ["FRESH", "STALE"],
            "should_not_retrieve": [],
            "expected_answer_pattern": r"no|hasn't changed",
            "expected_prefers_recent": True,
        }
        result = evaluate_contradiction_case(case, [chunk("FRESH"), chunk("STALE")])
        assert result["status"] == "FAIL"
        assert "answer did not match pattern" in result["reason"]

    def test_retrieval_coverage_reported_correctly(self, monkeypatch):
        import evals.kb_retrieval.recency_eval_runner as runner

        monkeypatch.setattr(
            runner, "_generate_answer",
            lambda case, chunks: "generic answer",
        )
        case = {
            "case_type": "contradiction",
            "query": "q",
            "should_retrieve": ["FRESH", "STALE", "MIDDLE"],
            "should_not_retrieve": [],
        }
        result = evaluate_contradiction_case(case, [chunk("FRESH"), chunk("STALE")])
        assert result["retrieval_coverage"] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Over-flagging-case assertions
# ---------------------------------------------------------------------------


class TestEvaluateOverFlaggingCase:
    def test_pass_when_answer_has_no_staleness_flag(self, monkeypatch):
        import evals.kb_retrieval.recency_eval_runner as runner

        monkeypatch.setattr(
            runner, "_generate_answer",
            lambda case, chunks: "RAG is a modern approach that grounds responses in retrieved context.",
        )
        case = {
            "case_type": "over_flagging",
            "query": "q",
            "should_retrieve": ["EVERGREEN"],
            "should_not_retrieve": [],
            "expected_no_staleness_flag": True,
        }
        result = evaluate_over_flagging_case(case, [chunk("EVERGREEN")])
        assert result["status"] == "PASS"

    def test_fail_when_answer_contains_staleness_flag(self, monkeypatch):
        import evals.kb_retrieval.recency_eval_runner as runner

        monkeypatch.setattr(
            runner, "_generate_answer",
            lambda case, chunks: "This source is outdated. RAG is a retrieval approach...",
        )
        case = {
            "case_type": "over_flagging",
            "query": "q",
            "should_retrieve": ["EVERGREEN"],
            "should_not_retrieve": [],
            "expected_no_staleness_flag": True,
        }
        result = evaluate_over_flagging_case(case, [chunk("EVERGREEN")])
        assert result["status"] == "FAIL"
        assert "staleness flag" in result["reason"]

    def test_fail_when_evergreen_doc_not_retrieved(self):
        # Retrieval-layer failure short-circuits the generation skip.
        case = {
            "case_type": "over_flagging",
            "query": "q",
            "should_retrieve": ["EVERGREEN"],
            "should_not_retrieve": [],
        }
        result = evaluate_over_flagging_case(case, [chunk("UNRELATED")])
        assert result["status"] == "FAIL"
        assert "evergreen doc not retrieved" in result["reason"]


class TestStalenessFlagDetector:
    def test_detects_common_staleness_prefaces(self):
        assert _contains_staleness_flag("This source is outdated. RAG is...")
        assert _contains_staleness_flag(
            "Note: this document may be outdated. RAG retrieves..."
        )
        assert _contains_staleness_flag("The text may no longer be accurate.")
        assert _contains_staleness_flag(
            "Caveat — this article is outdated, but..."
        )

    def test_does_not_flag_clean_answers(self):
        assert not _contains_staleness_flag(
            "RAG (Retrieval-Augmented Generation) is a pattern that..."
        )
        assert not _contains_staleness_flag(
            "Nate's most recent take is that agents are..."
        )

    def test_handles_empty_answer(self):
        assert not _contains_staleness_flag("")


# ---------------------------------------------------------------------------
# Control-case + signature collection + regression
# ---------------------------------------------------------------------------


class TestControlAndSignature:
    def test_control_case_records_signature(self):
        case = {
            "case_type": "control",
            "query": "What does Nate say about agents?",
            "should_retrieve": [],
            "should_not_retrieve": [],
        }
        chunks = [
            chunk("DOC1", score=0.812345, chunk_id="c1"),
            chunk("DOC2", score=0.701234, chunk_id="c2"),
        ]
        result = evaluate_control_case(case, chunks)
        assert result["status"] == "RECORDED"
        assert result["retrieved_chunk_signature"] == [
            ("c1", 0.812345),
            ("c2", 0.701234),
        ]

    def test_collect_off_state_signature_filters_to_control_only(self):
        # Only control rows feed the regression baseline — recency cases are
        # expected to *differ* between ENABLED states.
        results = [
            {
                "case_type": "recency",
                "query": "r-q",
                "retrieved_chunk_signature": [("c1", 0.7)],
            },
            {
                "case_type": "control",
                "query": "c-q",
                "retrieved_chunk_signature": [("c2", 0.6)],
            },
        ]
        sig = _collect_off_state_signature(results)
        assert sig == {"c-q": [("c2", 0.6)]}


class TestCompareSignatures:
    def test_identical_signatures_produce_no_diff(self):
        sig = {"q1": [("c1", 0.7)]}
        assert compare_signatures(sig, sig) == []

    def test_value_diff_reported(self):
        baseline = {"q1": [("c1", 0.7)]}
        current = {"q1": [("c1", 0.8)]}
        diffs = compare_signatures(baseline, current)
        assert len(diffs) == 1
        assert "signature changed" in diffs[0]

    def test_missing_query_reported(self):
        baseline = {"q1": [("c1", 0.7)], "q2": [("c2", 0.6)]}
        current = {"q1": [("c1", 0.7)]}
        diffs = compare_signatures(baseline, current)
        assert len(diffs) == 1
        assert "missing query in current" in diffs[0]

    def test_unexpected_query_reported(self):
        baseline = {"q1": [("c1", 0.7)]}
        current = {"q1": [("c1", 0.7)], "q2": [("c2", 0.6)]}
        diffs = compare_signatures(baseline, current)
        assert len(diffs) == 1
        assert "unexpected query in current" in diffs[0]


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_aggregate_counts_per_category(self):
        results = [
            {"case_type": "recency", "status": "PASS"},
            {"case_type": "recency", "status": "PASS"},
            {"case_type": "recency", "status": "FAIL"},
            {"case_type": "contradiction", "status": "SKIP-PENDING-KIN-485"},
            {"case_type": "over_flagging", "status": "SKIP-PENDING-KIN-485"},
            {"case_type": "control", "status": "RECORDED"},
        ]
        agg = aggregate_results(results)
        assert agg["recency"]["pass"] == 2
        assert agg["recency"]["fail"] == 1
        # aggregate_results() rounds pass_rate to 4dp for JSON cleanliness.
        assert agg["recency"]["pass_rate"] == pytest.approx(2 / 3, abs=1e-3)
        # Skip-only buckets have no denominator → pass_rate is None.
        assert agg["contradiction"]["skip"] == 1
        assert agg["contradiction"]["pass_rate"] is None

    def test_pass_rate_excludes_skipped_from_denominator(self):
        # 1 pass / 1 fail / 2 skip → pass_rate = 1 / (4 - 2) = 0.5
        results = [
            {"case_type": "recency", "status": "PASS"},
            {"case_type": "recency", "status": "FAIL"},
            {"case_type": "recency", "status": "SKIP-PENDING-KIN-485"},
            {"case_type": "recency", "status": "SKIP-PENDING-KIN-485"},
        ]
        agg = aggregate_results(results)
        assert agg["recency"]["pass_rate"] == 0.5


# ---------------------------------------------------------------------------
# End-to-end through evaluate_case dispatch — uses a fake retrieve via
# monkeypatch to keep the test sealed off from Supabase.
# ---------------------------------------------------------------------------


class TestEvaluateCaseDispatch:
    @pytest.mark.asyncio
    async def test_unknown_case_type_returns_error(self, monkeypatch):
        from evals.kb_retrieval import recency_eval_runner as runner

        async def fake_retrieve(*a, **kw):  # pragma: no cover — not called
            return []

        monkeypatch.setattr(runner, "_retrieve_chunks", fake_retrieve)
        result = await runner.evaluate_case(
            {"case_type": "nonsense", "query": "q"},
            scope=None,  # noqa: not used by fake
            scope_id=None,
            supabase=None,
        )
        assert result["status"] == "ERROR"
        assert "unknown case_type" in result["reason"]

    @pytest.mark.asyncio
    async def test_recency_dispatch_runs_assertion(self, monkeypatch):
        from evals.kb_retrieval import recency_eval_runner as runner

        async def fake_retrieve(query, scope, scope_id, supabase):
            return [chunk("FRESH"), chunk("STALE")]

        monkeypatch.setattr(runner, "_retrieve_chunks", fake_retrieve)
        result = await runner.evaluate_case(
            {
                "case_type": "recency",
                "query": "q",
                "should_retrieve": ["FRESH"],
                "should_not_retrieve": ["STALE"],
            },
            scope=None,
            scope_id=None,
            supabase=None,
        )
        assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# Shape sanity — _result_stub provides every field the report depends on.
# ---------------------------------------------------------------------------


class TestResultStub:
    def test_stub_carries_expected_fields(self):
        case = {
            "case_type": "recency",
            "query": "q",
            "should_retrieve": ["A"],
            "should_not_retrieve": ["B"],
        }
        stub = _result_stub(case, [chunk("A")])
        for key in (
            "query",
            "case_type",
            "should_retrieve",
            "should_not_retrieve",
            "retrieved_chunk_signature",
            "retrieved_doc_ranks",
            "num_chunks",
        ):
            assert key in stub
