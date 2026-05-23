"""Resolve title-pattern placeholders in dataset_recency.jsonl to real document_ids.

KIN-483 — recency-aware eval cases extend the KIN-449 format with
`fresh_doc_title_pattern` / `stale_doc_title_pattern`. This script connects
to a live Supabase agent KB, resolves the patterns to real UUIDs, picks the
*newest* matching doc as `fresh` and the *oldest* as `stale` (by
`document_date`, falling back to `created_at` when null), and emits a
populated JSONL ready for `eval_runner.py`.

Run after KIN-489 backfills `document_date` on the prod Nate corpus.

Usage:
    cd packages/api
    .venv/bin/python -m evals.kb_retrieval.populate_recency_dataset \\
        --agent-slug nate \\
        --input  evals/kb_retrieval/dataset_recency.jsonl \\
        --output evals/kb_retrieval/dataset_recency.populated.jsonl

Env vars (or CLI overrides): SUPABASE_URL, SUPABASE_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def resolve_agent_id(supabase, slug: str) -> str:
    """Look up agent_definition UUID from slug. Mirrors eval_runner.py."""
    result = (
        supabase.table("agent_definitions")
        .select("id, name, slug")
        .eq("slug", slug)
        .execute()
    )
    rows = result.data or []
    if not rows:
        _eprint(f"Error: no agent found with slug {slug!r}")
        sys.exit(1)
    _eprint(f"Resolved agent {slug!r} → {rows[0]['name']} ({rows[0]['id']})")
    return rows[0]["id"]


def load_documents(supabase, agent_id: str) -> list[dict]:
    """Fetch documents in the agent's KB ordered by document_date desc.

    Pulls knowledge_base_documents joined through knowledge_bases for the
    agent. NULL document_date sorts last (defaults to created_at fallback
    for ordering purposes).
    """
    kbs = (
        supabase.table("knowledge_bases")
        .select("id")
        .eq("agent_definition_id", agent_id)
        .execute()
    )
    kb_ids = [row["id"] for row in (kbs.data or [])]
    if not kb_ids:
        _eprint(f"Error: agent {agent_id} has no knowledge_bases")
        sys.exit(1)

    docs: list[dict] = []
    for kb_id in kb_ids:
        result = (
            supabase.table("knowledge_base_documents")
            .select("id, title, document_date, created_at, deleted_at")
            .eq("knowledge_base_id", kb_id)
            .is_("deleted_at", "null")
            .limit(2000)
            .execute()
        )
        docs.extend(result.data or [])

    # Sort newest → oldest by effective date (document_date preferred,
    # created_at fallback). Tuple sort: (has_real_date desc, date desc).
    def _key(d: dict):
        dd = d.get("document_date") or d.get("created_at") or ""
        return (1 if d.get("document_date") else 0, dd)

    docs.sort(key=_key, reverse=True)
    _eprint(f"Loaded {len(docs)} live documents from KB(s)")
    return docs


def match_pattern(docs: list[dict], pattern: str) -> list[dict]:
    """Return docs whose title contains the pattern substring (case-insensitive)."""
    if not pattern:
        return []
    needle = pattern.lower()
    return [d for d in docs if needle in (d.get("title") or "").lower()]


def pick_fresh_and_stale(
    docs: list[dict],
    fresh_pattern: str,
    stale_pattern: str,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve fresh / stale doc IDs from title patterns.

    * Fresh = newest doc matching fresh_pattern (or fresh==stale: pick newest of the bunch).
    * Stale = oldest doc matching stale_pattern (or fresh==stale: pick oldest of the bunch).
    * If a pattern has no matches → returns None for that slot; the case is
      logged as un-resolvable and emitted with the original placeholder.
    """
    fresh_matches = match_pattern(docs, fresh_pattern)
    stale_matches = match_pattern(docs, stale_pattern)

    if fresh_pattern == stale_pattern:
        if not fresh_matches:
            return None, None
        if len(fresh_matches) >= 2:
            # docs is sorted newest-first → first is freshest, last is stalest
            return fresh_matches[0]["id"], fresh_matches[-1]["id"]
        return fresh_matches[0]["id"], None  # single-doc pattern

    fresh_id = fresh_matches[0]["id"] if fresh_matches else None
    stale_id = stale_matches[-1]["id"] if stale_matches else None
    return fresh_id, stale_id


def populate_case(case: dict, docs: list[dict]) -> dict:
    """Resolve placeholders in one case. Returns a new dict; original untouched.

    Lines starting with `_comment` (the file header) pass through unchanged.
    """
    if "_comment" in case:
        return case

    fresh_pat = case.get("fresh_doc_title_pattern", "")
    stale_pat = case.get("stale_doc_title_pattern", "")

    fresh_id, stale_id = pick_fresh_and_stale(docs, fresh_pat, stale_pat)

    # Update should_retrieve / should_not_retrieve where placeholders sit.
    out = dict(case)
    new_should = []
    for item in case.get("should_retrieve") or []:
        if isinstance(item, str) and item.startswith("<") and item.endswith(">"):
            if fresh_id:
                new_should.append(fresh_id)
            else:
                new_should.append(item)  # leave placeholder, log later
        else:
            new_should.append(item)
    out["should_retrieve"] = new_should

    new_should_not = []
    for item in case.get("should_not_retrieve") or []:
        if isinstance(item, str) and item.startswith("<") and item.endswith(">"):
            if stale_id:
                new_should_not.append(stale_id)
            else:
                new_should_not.append(item)
        else:
            new_should_not.append(item)
    out["should_not_retrieve"] = new_should_not

    out["_resolved_fresh_doc_id"] = fresh_id
    out["_resolved_stale_doc_id"] = stale_id
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate dataset_recency.jsonl placeholders with live document_ids (KIN-483)",
    )
    parser.add_argument("--agent-slug", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        _eprint("Error: SUPABASE_URL and SUPABASE_KEY required.")
        return 1

    from supabase import create_client  # local import keeps script standalone

    supabase = create_client(args.supabase_url, args.supabase_key)
    agent_id = resolve_agent_id(supabase, args.agent_slug)
    docs = load_documents(supabase, agent_id)

    with open(args.input) as f:
        cases = [json.loads(line) for line in f if line.strip()]
    _eprint(f"Read {len(cases)} input cases from {args.input}")

    resolved_count = 0
    unresolved: list[tuple[int, str, str]] = []
    populated: list[dict] = []

    for i, case in enumerate(cases):
        out = populate_case(case, docs)
        populated.append(out)
        if "_comment" in case:
            continue
        fresh_id = out.get("_resolved_fresh_doc_id")
        stale_id = out.get("_resolved_stale_doc_id")
        fresh_pat = case.get("fresh_doc_title_pattern", "")
        stale_pat = case.get("stale_doc_title_pattern", "")

        if fresh_id or stale_id:
            resolved_count += 1
        if fresh_pat and not fresh_id:
            unresolved.append((i, "fresh", fresh_pat))
        if stale_pat and stale_pat != fresh_pat and not stale_id:
            unresolved.append((i, "stale", stale_pat))

    with open(args.output, "w") as f:
        for case in populated:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    _eprint(f"\nResolved {resolved_count} cases (at least partially).")
    _eprint(f"Wrote {len(populated)} lines to {args.output}.")
    if unresolved:
        _eprint(f"\n{len(unresolved)} unresolved patterns (left as placeholders):")
        for idx, slot, pat in unresolved[:25]:
            _eprint(f"  case[{idx}] {slot}: {pat!r}")
        if len(unresolved) > 25:
            _eprint(f"  ... and {len(unresolved) - 25} more")
        _eprint("\nVerify the agent KB contains documents matching these patterns "
                "(post-KIN-489 backfill should cover all 567 Nate articles).")
        return 2

    _eprint("\nAll patterns resolved. Dataset ready to feed eval_runner.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
