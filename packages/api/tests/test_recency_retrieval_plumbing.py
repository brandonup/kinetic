"""KIN-482 — `match_chunks` RPC plumbing: surface `effective_date` to retrieval.

Covers the Python-side changes in this ticket. The migration itself
(`packages/api/migrations/20260523000001_match_chunks_add_effective_date.sql`)
is applied to dev Supabase via the SQL Editor — there is no offline test
harness for the PL/pgSQL function; that gate is the live-invocation verification
required by `policies/database-migrations.md` §2a (KIN-478 cautionary tale).

What pytest covers here:
* `_parse_iso_date` — string / date / None / malformed
* `_derive_effective_date` — both-tail clamp, COALESCE precedence, fallback row
* `_normalise_search_row` — surfaces the new keys on RPC and fallback paths
* `RetrievedChunk` — new fields default correctly, propagate through citation
  assembly (no need to exercise the full pipeline; we test the structural fields)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# _parse_iso_date
# ---------------------------------------------------------------------------


class TestParseIsoDate:
    def test_string_yyyy_mm_dd(self):
        from app.services.rag.retrieval import _parse_iso_date

        assert _parse_iso_date("2026-01-31") == date(2026, 1, 31)

    def test_string_with_trailing_garbage_truncated(self):
        """PostgREST returns plain `YYYY-MM-DD` for `date`, but be liberal."""
        from app.services.rag.retrieval import _parse_iso_date

        assert _parse_iso_date("2026-01-31T00:00:00Z") == date(2026, 1, 31)

    def test_existing_date_passthrough(self):
        from app.services.rag.retrieval import _parse_iso_date

        d = date(2026, 1, 31)
        assert _parse_iso_date(d) is d

    def test_none_returns_none(self):
        from app.services.rag.retrieval import _parse_iso_date

        assert _parse_iso_date(None) is None

    def test_empty_string_returns_none(self):
        from app.services.rag.retrieval import _parse_iso_date

        assert _parse_iso_date("") is None

    def test_unparseable_returns_none(self):
        from app.services.rag.retrieval import _parse_iso_date

        assert _parse_iso_date("not-a-date") is None
        assert _parse_iso_date(12345) is None


# ---------------------------------------------------------------------------
# _derive_effective_date — COALESCE + both-tail clamp
# ---------------------------------------------------------------------------


class TestDeriveEffectiveDate:
    def test_real_document_date_wins(self):
        """When document_date is plausible, it is the effective date and not estimated."""
        from app.services.rag.retrieval import _derive_effective_date

        eff, est = _derive_effective_date({
            "document_date": "2026-01-31",
            "document_created_at": "2026-03-01",
        })
        assert eff == date(2026, 1, 31)
        assert est is False

    def test_null_document_date_falls_back_to_created_at(self):
        from app.services.rag.retrieval import _derive_effective_date

        eff, est = _derive_effective_date({
            "document_date": None,
            "document_created_at": "2026-03-01",
        })
        assert eff == date(2026, 3, 1)
        assert est is True

    def test_pre_2015_document_date_is_discarded_falls_back(self):
        """An implausibly-old document_date (e.g. datetime.min sentinel) falls back."""
        from app.services.rag.retrieval import _derive_effective_date

        eff, est = _derive_effective_date({
            "document_date": "1999-01-01",
            "document_created_at": "2026-03-01",
        })
        assert eff == date(2026, 3, 1)
        assert est is True

    def test_far_future_document_date_is_discarded_falls_back(self):
        from app.services.rag.retrieval import _derive_effective_date

        far_future = (_today_utc() + timedelta(days=30)).isoformat()
        eff, est = _derive_effective_date({
            "document_date": far_future,
            "document_created_at": "2026-03-01",
        })
        assert eff == date(2026, 3, 1)
        assert est is True

    def test_no_dates_yields_none(self):
        """Fallback search path: neither column present → recency is a no-op for this chunk."""
        from app.services.rag.retrieval import _derive_effective_date

        eff, est = _derive_effective_date({})
        assert eff is None
        assert est is False

    def test_document_date_present_but_created_at_missing(self):
        """Real publish date alone is fine even without created_at."""
        from app.services.rag.retrieval import _derive_effective_date

        eff, est = _derive_effective_date({"document_date": "2026-01-31"})
        assert eff == date(2026, 1, 31)
        assert est is False

    def test_today_plus_one_is_plausible_boundary(self):
        """Boundary check — today+1d is allowed (clock skew margin)."""
        from app.services.rag.retrieval import _derive_effective_date

        boundary = (_today_utc() + timedelta(days=1)).isoformat()
        eff, est = _derive_effective_date({
            "document_date": boundary,
            "document_created_at": "2025-01-01",
        })
        assert eff == _today_utc() + timedelta(days=1)
        assert est is False


# ---------------------------------------------------------------------------
# _normalise_search_row
# ---------------------------------------------------------------------------


class TestNormaliseSearchRow:
    def _base_rpc_row(self):
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "document_id": "22222222-2222-2222-2222-222222222222",
            "document_title": "Some Article",
            "document_type": "text/plain",
            "text": "chunk body",
            "chunk_index": 0,
            "section_path": None,
            "page_range": None,
            "similarity": 0.78,
        }

    def test_rpc_row_with_real_document_date(self):
        from app.services.rag.retrieval import _normalise_search_row

        row = self._base_rpc_row()
        row["document_date"] = "2026-01-31"
        row["document_created_at"] = "2026-03-01"
        result = _normalise_search_row(row)
        assert result["effective_date"] == date(2026, 1, 31)
        assert result["date_is_estimated"] is False

    def test_rpc_row_with_null_document_date_falls_back(self):
        from app.services.rag.retrieval import _normalise_search_row

        row = self._base_rpc_row()
        row["document_date"] = None
        row["document_created_at"] = "2026-03-01"
        result = _normalise_search_row(row)
        assert result["effective_date"] == date(2026, 3, 1)
        assert result["date_is_estimated"] is True

    def test_fallback_search_row_yields_no_effective_date(self):
        """Fallback select does not return date columns → effective_date is None, not estimated."""
        from app.services.rag.retrieval import _normalise_search_row

        # Shape of a fallback row (PostgREST join — date cols absent)
        fallback_row = {
            "id": "33333333-3333-3333-3333-333333333333",
            "document_id": "44444444-4444-4444-4444-444444444444",
            "text": "body",
            "embedding": [0.1] * 3072,
            "chunk_index": 0,
            "section_path": None,
            "page_range": None,
            "knowledge_base_documents": {
                "title": "From Join",
                "file_type": "text/plain",
                "deleted_at": None,
            },
            "similarity": 0.42,
        }
        result = _normalise_search_row(fallback_row)
        assert result["document_title"] == "From Join"
        assert result["effective_date"] is None
        assert result["date_is_estimated"] is False

    def test_existing_keys_unchanged_by_addition(self):
        """The new keys don't disturb the existing 9-column shape."""
        from app.services.rag.retrieval import _normalise_search_row

        row = self._base_rpc_row()
        row["document_date"] = "2026-01-31"
        row["document_created_at"] = "2026-03-01"
        result = _normalise_search_row(row)
        expected_existing_keys = {
            "chunk_id", "document_id", "document_title", "document_type",
            "text", "chunk_index", "section_path", "page_range",
            "similarity_score", "embedding",
        }
        assert expected_existing_keys.issubset(set(result.keys()))
        # Plus the two new ones
        assert {"effective_date", "date_is_estimated"}.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# RetrievedChunk dataclass — new fields default & accept properly
# ---------------------------------------------------------------------------


class TestRetrievedChunkDates:
    def _kwargs(self):
        return dict(
            chunk_id="c", document_id="d", document_title="t", document_type=None,
            text="x", chunk_index=0, section_path=None, page_range=None,
            similarity_score=0.5,
        )

    def test_defaults_to_none_and_false(self):
        from app.services.rag.retrieval import RetrievedChunk

        c = RetrievedChunk(**self._kwargs())
        assert c.effective_date is None
        assert c.date_is_estimated is False

    def test_accepts_explicit_date(self):
        from app.services.rag.retrieval import RetrievedChunk

        c = RetrievedChunk(
            **self._kwargs(),
            effective_date=date(2026, 1, 31),
            date_is_estimated=False,
        )
        assert c.effective_date == date(2026, 1, 31)
        assert c.date_is_estimated is False

    def test_accepts_estimated_flag(self):
        from app.services.rag.retrieval import RetrievedChunk

        c = RetrievedChunk(
            **self._kwargs(),
            effective_date=date(2026, 3, 1),
            date_is_estimated=True,
        )
        assert c.date_is_estimated is True
