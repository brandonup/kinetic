"""Unit tests for preseed_dedup.py (KIN-490)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from preseed_dedup import (
    build_dedup_rows,
    extract_slug_from_url,
    fetch_kb_slugs,
)


# ---------------------------------------------------------------------------
# extract_slug_from_url
# ---------------------------------------------------------------------------

class TestExtractSlugFromUrl:
    def test_standard_url(self):
        assert extract_slug_from_url(
            "https://natesnewsletter.substack.com/p/beat-the-95-ai-fail-rate"
        ) == "beat-the-95-ai-fail-rate"

    def test_strips_query_string(self):
        assert extract_slug_from_url(
            "https://natesnewsletter.substack.com/p/some-slug?utm_source=email"
        ) == "some-slug"

    def test_strips_fragment(self):
        assert extract_slug_from_url(
            "https://natesnewsletter.substack.com/p/some-slug#section"
        ) == "some-slug"

    def test_strips_trailing_slash(self):
        assert extract_slug_from_url(
            "https://natesnewsletter.substack.com/p/some-slug/"
        ) == "some-slug"

    def test_no_p_segment_returns_none(self):
        assert extract_slug_from_url("https://natesnewsletter.substack.com/") is None

    def test_empty_string_returns_none(self):
        assert extract_slug_from_url("") is None

    def test_none_handled_via_empty(self):
        # callers always pass str(url or "")
        assert extract_slug_from_url("") is None


# ---------------------------------------------------------------------------
# build_dedup_rows — original behaviour (no known_slugs)
# ---------------------------------------------------------------------------

class TestBuildDedup_NoFilter:
    def _make_posts(self, n: int = 3) -> list[dict]:
        return [
            {
                "id": i + 1,
                "canonical_url": f"https://natesnewsletter.substack.com/p/post-{i}",
                "title": f"Post {i}",
            }
            for i in range(n)
        ]

    def test_returns_three_tuple(self):
        rows, skipped_no_id, orphans = build_dedup_rows(self._make_posts(), "src-1", "user-1")
        assert isinstance(rows, list)
        assert isinstance(skipped_no_id, int)
        assert isinstance(orphans, int)

    def test_all_posts_included_without_filter(self):
        posts = self._make_posts(5)
        rows, skipped_no_id, orphans = build_dedup_rows(posts, "src-1", "user-1")
        assert len(rows) == 5
        assert skipped_no_id == 0
        assert orphans == 0

    def test_posts_without_id_skipped(self):
        posts = [
            {"id": 1, "canonical_url": "https://x.com/p/slug-a", "title": "A"},
            {"canonical_url": "https://x.com/p/slug-b", "title": "B"},  # no id
        ]
        rows, skipped_no_id, orphans = build_dedup_rows(posts, "src-1", "user-1")
        assert len(rows) == 1
        assert skipped_no_id == 1
        assert orphans == 0

    def test_row_fields(self):
        posts = [{"id": 42, "canonical_url": "https://x.com/p/my-slug", "title": "My Title"}]
        rows, _, _ = build_dedup_rows(posts, "src-99", "user-99")
        assert rows[0] == {
            "scrape_source_id": "src-99",
            "user_id": "user-99",
            "external_id": "42",
            "url": "https://x.com/p/my-slug",
            "title": "My Title",
        }

    def test_external_id_is_string(self):
        posts = [{"id": 100, "canonical_url": "https://x.com/p/x", "title": "X"}]
        rows, _, _ = build_dedup_rows(posts, "s", "u")
        assert rows[0]["external_id"] == "100"


# ---------------------------------------------------------------------------
# build_dedup_rows — with known_slugs filter (Option A)
# ---------------------------------------------------------------------------

class TestBuildDedup_WithFilter:
    def _posts(self) -> list[dict]:
        return [
            {"id": 1, "canonical_url": "https://x.com/p/in-kb", "title": "In KB"},
            {"id": 2, "canonical_url": "https://x.com/p/not-in-kb", "title": "Not in KB"},
            {"id": 3, "canonical_url": "https://x.com/p/also-in-kb", "title": "Also in KB"},
        ]

    def test_only_matching_slugs_included(self):
        known = {"in-kb", "also-in-kb"}
        rows, skipped_no_id, orphans = build_dedup_rows(
            self._posts(), "src", "user", known_slugs=known
        )
        assert len(rows) == 2
        assert {r["external_id"] for r in rows} == {"1", "3"}
        assert orphans == 1
        assert skipped_no_id == 0

    def test_none_known_slugs_no_filtering(self):
        rows, _, orphans = build_dedup_rows(self._posts(), "src", "user", known_slugs=None)
        assert len(rows) == 3
        assert orphans == 0

    def test_empty_known_slugs_all_orphans(self):
        rows, skipped_no_id, orphans = build_dedup_rows(
            self._posts(), "src", "user", known_slugs=set()
        )
        assert len(rows) == 0
        assert orphans == 3
        assert skipped_no_id == 0

    def test_all_slugs_match(self):
        known = {"in-kb", "not-in-kb", "also-in-kb"}
        rows, _, orphans = build_dedup_rows(
            self._posts(), "src", "user", known_slugs=known
        )
        assert len(rows) == 3
        assert orphans == 0

    def test_missing_canonical_url_treated_as_orphan(self):
        posts = [{"id": 9, "canonical_url": "", "title": "No URL"}]
        rows, _, orphans = build_dedup_rows(
            posts, "src", "user", known_slugs={"some-slug"}
        )
        assert len(rows) == 0
        assert orphans == 1

    def test_slug_not_in_known_still_skipped_no_id(self):
        posts = [
            {"canonical_url": "https://x.com/p/in-kb", "title": "No ID"},  # no id
        ]
        rows, skipped_no_id, orphans = build_dedup_rows(
            posts, "src", "user", known_slugs={"in-kb"}
        )
        assert len(rows) == 0
        assert skipped_no_id == 1
        assert orphans == 0


# ---------------------------------------------------------------------------
# fetch_kb_slugs
# ---------------------------------------------------------------------------

class TestFetchKbSlugs:
    def _make_response(self, titles: list[str], status_code: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.raise_for_status.return_value = None
        resp.json.return_value = [{"title": t} for t in titles]
        return resp

    @patch("preseed_dedup.requests.get")
    def test_strips_txt_extension(self, mock_get):
        mock_get.return_value = self._make_response(["beat-the-ai.txt", "some-slug.txt"])
        slugs = fetch_kb_slugs("https://x.supabase.co", "key", "kb-uuid")
        assert slugs == {"beat-the-ai", "some-slug"}

    @patch("preseed_dedup.requests.get")
    def test_skips_prose_titles(self, mock_get):
        mock_get.return_value = self._make_response([
            "AI made your app teams 10x faster. Nobody gave your platform team 10x the headcount.",
            "valid-slug.txt",
        ])
        slugs = fetch_kb_slugs("https://x.supabase.co", "key", "kb-uuid")
        assert slugs == {"valid-slug"}

    @patch("preseed_dedup.requests.get")
    def test_slug_without_txt_no_spaces_included(self, mock_get):
        # A title that's already a slug (no .txt, no spaces) should still be included
        mock_get.return_value = self._make_response(["plain-slug"])
        slugs = fetch_kb_slugs("https://x.supabase.co", "key", "kb-uuid")
        assert "plain-slug" in slugs

    @patch("preseed_dedup.requests.get")
    def test_empty_kb_returns_empty_set(self, mock_get):
        mock_get.return_value = self._make_response([])
        slugs = fetch_kb_slugs("https://x.supabase.co", "key", "kb-uuid")
        assert slugs == set()

    @patch("preseed_dedup.requests.get")
    def test_pagination_fetches_all(self, mock_get):
        batch1 = [{"title": f"slug-{i}.txt"} for i in range(1000)]
        batch2 = [{"title": f"slug-{i}.txt"} for i in range(1000, 1050)]

        resp1 = MagicMock()
        resp1.raise_for_status.return_value = None
        resp1.json.return_value = batch1

        resp2 = MagicMock()
        resp2.raise_for_status.return_value = None
        resp2.json.return_value = batch2

        mock_get.side_effect = [resp1, resp2]
        slugs = fetch_kb_slugs("https://x.supabase.co", "key", "kb-uuid")
        assert len(slugs) == 1050
