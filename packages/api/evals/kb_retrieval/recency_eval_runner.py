"""
Recency-aware eval runner (KIN-492 / recency-plan Task 6).

Forks the KIN-449 eval runner (`eval_runner.py`) rather than extending it —
per ticket scope: keep the KIN-449 runner stable and free of recency-specific
branching. This runner reads the same JSONL format (plus the KIN-483 extension
fields) and dispatches per `case_type`:

    recency        — retrieval-side: assert the fresh doc ranks above the
                     stale near-duplicate in the chunk list.
    contradiction  — retrieval-side: assert both fresh and stale docs are
                     retrieved. Generation-side: assert the answer prefers
                     the recent source.
    over_flagging  — retrieval-side: assert the evergreen doc is retrieved.
                     Generation-side: assert NO staleness flag string in
                     the answer.
    control        — record the chunk-id signature for the off-state
                     byte-identical regression check.

Generation-side assertions are scaffolded but **skipped** with status
``PENDING-KIN-485`` until Component D (date-aware generation) ships. The
runner reports per-case PASS / FAIL / SKIP-PENDING plus aggregate pass
rates by case_type.

Two execution modes:

* **standard**          — score every case in the dataset and emit a report.
* **--regression-check**— compare the current off-state retrieval output for
                          the control cases against a committed baseline
                          snapshot; exit non-zero on any byte difference.
                          Use ``--write-baseline`` to capture the initial
                          snapshot.

Usage:

    cd packages/api

    # Standard recency-on pass
    RECENCY_ENABLED=true RECENCY_WEIGHT=0.15 \\
      .venv/bin/python -m evals.kb_retrieval.recency_eval_runner \\
      --dataset evals/kb_retrieval/dataset_recency.populated.jsonl \\
      --agent-slug nate

    # Capture the off-state baseline snapshot (one-time)
    .venv/bin/python -m evals.kb_retrieval.recency_eval_runner \\
      --dataset evals/kb_retrieval/dataset_recency.populated.jsonl \\
      --agent-slug nate \\
      --write-baseline evals/kb_retrieval/off_state_baseline.json

    # Regression check — fails CI / smoke test on any byte diff
    .venv/bin/python -m evals.kb_retrieval.recency_eval_runner \\
      --dataset evals/kb_retrieval/dataset_recency.populated.jsonl \\
      --agent-slug nate \\
      --regression-check evals/kb_retrieval/off_state_baseline.json

Env vars (or CLI overrides):
    SUPABASE_URL, SUPABASE_KEY                — required for retrieval.
    RECENCY_ENABLED, RECENCY_WEIGHT           — read by retrieve() via settings;
                                                the runner forces RECENCY_ENABLED
                                                off for control cases regardless.
    EVAL_GENERATION_MODEL                     — model used by _generate_answer
                                                for contradiction / over_flagging
                                                cases. Defaults to gpt-4o-mini.
    EVAL_GENERATION_API_KEY                   — BYOK key for the generation
                                                model's provider. Required when
                                                running contradiction or
                                                over_flagging cases (KIN-495).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

# Add packages/api to path so app imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_dotenv() -> None:
    """Load env from packages/api/.env.prod (preferred) then .env as fallback.

    .env.prod should carry prod SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY so
    the eval runner hits the real Nate KB. The local .env points at dev which
    has no documents. Create .env.prod from Railway → Variables if missing.
    """
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    for name in (".env.prod", ".env"):
        path = os.path.join(base, name)
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
            break  # stop after first file found
        except FileNotFoundError:
            continue


_load_dotenv()

from app.services.rag.retrieval import (  # noqa: E402
    RetrievalScope,
    retrieve,
)

# Reuse KIN-449 agent-slug resolver verbatim — stable surface.
from evals.kb_retrieval.eval_runner import resolve_agent_id  # noqa: E402


# ---------------------------------------------------------------------------
# Dataset loading + populated-vs-template detection
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"^<.+_doc_id_\w+>$")


def load_dataset(path: str) -> list[dict]:
    """Load a JSONL dataset, dropping comment-only lines."""
    with open(path) as f:
        cases: list[dict] = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if set(row.keys()) == {"_comment"}:
                continue
            cases.append(row)
    return cases


def is_dataset_populated(cases: list[dict]) -> tuple[bool, list[str]]:
    """Return ``(populated, offending_ids)``.

    A populated dataset has every ``should_retrieve`` / ``should_not_retrieve``
    entry resolved to a real UUID. Template placeholders like
    ``<fresh_doc_id_1>`` are the unpopulated state — running against the
    template silently produces 0% recall (per recency_cases_README.md).
    """
    offending: list[str] = []
    for case in cases:
        for key in ("should_retrieve", "should_not_retrieve"):
            for value in case.get(key, []) or []:
                if isinstance(value, str) and _PLACEHOLDER_RE.match(value):
                    offending.append(value)
    return (len(offending) == 0, offending)


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------

# Generation-layer dependency on Component D (KIN-485, KIN-495). Now True —
# `_generate_answer` is wired to the same prompt + RAG-context-assembly path
# the FastAPI chat endpoint uses, gated on `RECENCY_ENABLED` so the date-aware
# v2 system prompt + Published/Added source lines are exercised under the same
# flag the prod generation path is. Set `EVAL_GENERATION_MODEL` /
# `EVAL_GENERATION_API_KEY` env vars to override the model + key.
GENERATION_AVAILABLE = True


async def _retrieve_chunks(
    query: str,
    scope: RetrievalScope,
    scope_id: UUID,
    supabase,
) -> list:
    """Run retrieve() for the eval — the same shape KIN-449 uses, sans the
    stale ``openai_key`` kwarg that pre-dated the KIN-467 Gemini switch."""
    return await retrieve(
        query_text=query,
        scope=scope,
        scope_id=scope_id,
        supabase=supabase,
        model_context_window=1_000_000,
        vector_top_k=20,
        mmr_top_k=20,
        similarity_threshold=0.3,
    )


def _doc_ranks(chunks) -> dict[str, int]:
    """Map document_id → first-occurrence rank (1-indexed) in the chunk list."""
    ranks: dict[str, int] = {}
    for rank, chunk in enumerate(chunks, 1):
        if chunk.document_id not in ranks:
            ranks[chunk.document_id] = rank
    return ranks


# ---------------------------------------------------------------------------
# Per-case-type assertions
# ---------------------------------------------------------------------------


def _result_stub(case: dict, chunks) -> dict:
    """Build the common result-row scaffold every assertion fills in."""
    return {
        "query": case["query"],
        "case_type": case.get("case_type"),
        "should_retrieve": list(case.get("should_retrieve") or []),
        "should_not_retrieve": list(case.get("should_not_retrieve") or []),
        "retrieved_chunk_signature": [
            (c.chunk_id, round(c.similarity_score, 6)) for c in chunks
        ],
        "retrieved_doc_ranks": _doc_ranks(chunks),
        "num_chunks": len(chunks),
    }


def evaluate_recency_case(case: dict, chunks) -> dict:
    """Assert: the fresh doc ranks above the stale doc.

    PASS when both docs are retrieved AND fresh rank < stale rank.
    SKIP-EMPTY when the stale ID is missing (single-doc probes — the dataset
    has one case like that where there is no near-duplicate).
    FAIL otherwise.
    """
    result = _result_stub(case, chunks)
    should = case.get("should_retrieve") or []
    should_not = case.get("should_not_retrieve") or []
    ranks = result["retrieved_doc_ranks"]

    fresh_id = should[0] if should else None
    stale_id = should_not[0] if should_not else None

    if fresh_id is None:
        result["status"] = "ERROR"
        result["reason"] = "no fresh doc id"
        return result

    fresh_rank = ranks.get(fresh_id)

    # Single-doc probe — no stale near-duplicate; just confirm the fresh doc
    # is retrieved at all.
    if stale_id is None:
        if fresh_rank is None:
            result["status"] = "FAIL"
            result["reason"] = "fresh doc not retrieved"
        else:
            result["status"] = "PASS"
            result["fresh_rank"] = fresh_rank
        return result

    stale_rank = ranks.get(stale_id)
    if fresh_rank is None:
        result["status"] = "FAIL"
        result["reason"] = "fresh doc not retrieved"
    elif stale_rank is None:
        # The recency feature is supposed to demote the stale — but if it
        # is missing entirely, the stale-vs-fresh comparison is undefined.
        # Treat as PASS (no stale to demote == recency satisfied) and note.
        result["status"] = "PASS"
        result["fresh_rank"] = fresh_rank
        result["reason"] = "stale doc not retrieved (no comparison needed)"
    elif fresh_rank < stale_rank:
        result["status"] = "PASS"
        result["fresh_rank"] = fresh_rank
        result["stale_rank"] = stale_rank
    else:
        result["status"] = "FAIL"
        result["reason"] = (
            f"stale doc ranks above fresh (fresh={fresh_rank}, stale={stale_rank})"
        )
        result["fresh_rank"] = fresh_rank
        result["stale_rank"] = stale_rank
    return result


def evaluate_contradiction_case(case: dict, chunks) -> dict:
    """Retrieval part runs; generation-side assertion skipped pending KIN-485.

    Retrieval-side requirement: both fresh and stale candidates should be in
    the retrieved set so the generation layer has both perspectives to weigh.
    Generation-side: ``expected_answer_pattern`` regex + ``expected_prefers_recent``.
    """
    result = _result_stub(case, chunks)
    ranks = result["retrieved_doc_ranks"]
    should = case.get("should_retrieve") or []

    retrieved_count = sum(1 for did in should if did in ranks)
    result["retrieval_coverage"] = (
        retrieved_count / len(should) if should else 0.0
    )

    if not GENERATION_AVAILABLE:
        result["status"] = "SKIP-PENDING-KIN-485"
        result["reason"] = (
            "Component D not shipped — answer-text assertions cannot run yet"
        )
        result["expected_answer_pattern"] = case.get("expected_answer_pattern")
        result["expected_prefers_recent"] = case.get("expected_prefers_recent")
        return result

    # KIN-495: Component D wired — run the answer-pattern assertion.
    try:
        answer = _generate_answer(case, chunks)
    except Exception as exc:
        result["status"] = "ERROR"
        result["reason"] = f"generation failed: {exc}"
        return result
    pattern = case.get("expected_answer_pattern") or ""
    if pattern and not re.search(pattern, answer, re.IGNORECASE):
        result["status"] = "FAIL"
        result["reason"] = f"answer did not match pattern {pattern!r}"
    else:
        result["status"] = "PASS"
    result["answer"] = answer
    return result


def evaluate_over_flagging_case(case: dict, chunks) -> dict:
    """Retrieval part runs; generation-side assertion skipped pending KIN-485.

    Retrieval-side requirement: the evergreen doc is retrieved.
    Generation-side: the answer does NOT contain a staleness-warning string.
    """
    result = _result_stub(case, chunks)
    ranks = result["retrieved_doc_ranks"]
    should = case.get("should_retrieve") or []

    if should and not any(did in ranks for did in should):
        result["status"] = "FAIL"
        result["reason"] = "evergreen doc not retrieved"
        return result

    if not GENERATION_AVAILABLE:
        result["status"] = "SKIP-PENDING-KIN-485"
        result["reason"] = (
            "Component D not shipped — staleness-flag assertion cannot run yet"
        )
        result["expected_no_staleness_flag"] = case.get("expected_no_staleness_flag")
        return result

    # KIN-495: Component D wired — run the staleness-flag assertion.
    try:
        answer = _generate_answer(case, chunks)
    except Exception as exc:
        result["status"] = "ERROR"
        result["reason"] = f"generation failed: {exc}"
        return result
    if _contains_staleness_flag(answer):
        result["status"] = "FAIL"
        result["reason"] = "answer contained a spurious staleness flag"
    else:
        result["status"] = "PASS"
    result["answer"] = answer
    return result


def evaluate_control_case(case: dict, chunks) -> dict:
    """Control cases are the off-state byte-identical regression substrate.

    The runner records the chunk-id + similarity signature; the regression
    mode (--regression-check) compares this signature across runs.
    """
    result = _result_stub(case, chunks)
    result["status"] = "RECORDED"
    return result


# Generation-side stubs — implementations land with KIN-485.

_STALENESS_FLAG_PATTERNS = [
    r"this source (?:is|may be) outdated",
    r"this (?:document|article) (?:is|may be) outdated",
    r"may no longer be accurate",
    r"outdated information",
]


def _contains_staleness_flag(answer: str) -> bool:
    """Heuristic match for staleness-warning prefaces in an LLM answer.

    Exposed publicly so the runner self-tests can lock the regex set without
    needing live generation. Patterns derived from the contradiction
    instruction proposed in the recency design § Component D.
    """
    if not answer:
        return False
    lower = answer.lower()
    return any(re.search(p, lower) for p in _STALENESS_FLAG_PATTERNS)


# Default model used when EVAL_GENERATION_MODEL is unset. Cheap + fast — the
# eval cares about whether the model honours the date instructions, not
# whether it's the strongest model available.
_DEFAULT_EVAL_MODEL = "gpt-4o-mini"


async def _generate_answer_async(case: dict, chunks) -> str:
    """Run the date-aware generation pipeline end-to-end for one eval case.

    Mirrors the FastAPI `generate` endpoint's prompt-assembly path (KIN-485 /
    `generation.py` step 7) without touching Supabase or auth:

      1. Build the per-chunk source header through the SAME helper the API
         uses (`context_assembler._format_source_header`) so the dates land in
         exactly the format the prompt-template assumes — `Published: YYYY-MM-DD`
         when `date_is_estimated=False`, `Added: YYYY-MM-DD` otherwise. The
         helper itself honours `settings.RECENCY_ENABLED`, so the eval only
         exercises date-aware behaviour when the same gate the runtime path
         uses is on.
      2. Pick the v2 (date-aware) system template when RECENCY_ENABLED, else
         v1 — identical branch logic to `generation.py`. Off-state must be
         byte-identical to pre-feature.
      3. Stream the LLM response via `stream_llm` and concatenate deltas. We
         deliberately do NOT route through the conversation/messages tables —
         the eval is a fresh single-turn invocation per case.

    Env vars:
        EVAL_GENERATION_MODEL    — model name (default ``gpt-4o-mini``).
        EVAL_GENERATION_API_KEY  — BYOK key for the model's provider.

    Raises:
        RuntimeError if no API key is configured. Caller is expected to set
        the key in the eval shell session — same posture as `SUPABASE_KEY`.
    """
    from app.core.config import settings as _settings
    from app.services.context_assembler import _format_source_header
    from app.services.prompts import get_prompt
    from app.services.llm_client import stream_llm

    api_key = os.environ.get("EVAL_GENERATION_API_KEY")
    if not api_key:
        raise RuntimeError(
            "EVAL_GENERATION_API_KEY not set — eval cannot stream the LLM. "
            "Set this to a BYOK key for the EVAL_GENERATION_MODEL's provider."
        )
    model = os.environ.get("EVAL_GENERATION_MODEL", _DEFAULT_EVAL_MODEL)

    # Step 1: RAG-context block, identical format to ContextAssembler._assemble_rag.
    recency_enabled = _settings.RECENCY_ENABLED
    if chunks:
        rag_lines = [
            f"{_format_source_header(c, recency_enabled=recency_enabled)}\n{c.text}"
            for c in chunks
        ]
        rag_context = "\n\n".join(rag_lines)
    else:
        rag_context = ""

    # Step 2: prompt template — v2 when RECENCY_ENABLED, else v1 (byte-identical
    # to the off-state branch in generation.py).
    prompt_id = (
        "context-stack-system-v2" if recency_enabled else "context-stack-system-v1"
    )
    system_template = get_prompt(prompt_id, "system")
    # `context_layers` is empty in eval mode — the runner only exercises L8/L9
    # RAG signals, not the upstream L1-L7 stack. That keeps the contradiction /
    # over-flagging assertions strictly about date-aware behaviour.
    system_content = system_template.format(
        context_layers="", rag_context=rag_context
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": case["query"]},
    ]

    # Step 3: stream and concatenate.
    parts: list[str] = []
    async for delta in stream_llm(
        messages=messages,
        model=model,
        api_key=api_key,
        temperature=0.0,  # deterministic — eval reproducibility
    ):
        parts.append(delta)
    return "".join(parts)


def _generate_answer(case: dict, chunks) -> str:
    """Sync wrapper around `_generate_answer_async`.

    The case-evaluator dispatch is sync (case_type → handler returns a dict),
    so we bridge via `asyncio.run_coroutine_threadsafe` when an event loop is
    already running, else a plain `asyncio.run`. The runner's main loop awaits
    `evaluate_case` from within an event loop, so we use `asyncio.run` only in
    contexts without one (e.g. self-tests calling the evaluator directly with
    a pre-mocked `_generate_answer`).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_generate_answer_async(case, chunks))

    # We are inside the runner's event loop — schedule and block.
    # `asyncio.run` would error with "asyncio.run() cannot be called from a
    # running event loop", so use the thread-safe future trick. The evaluator
    # functions are sync; running the coroutine on a fresh thread is the
    # simplest way to bridge without rewriting the whole dispatch layer.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(asyncio.run, _generate_answer_async(case, chunks))
        return fut.result()


# ---------------------------------------------------------------------------
# Dispatch + aggregation
# ---------------------------------------------------------------------------

_DISPATCH = {
    "recency": evaluate_recency_case,
    "contradiction": evaluate_contradiction_case,
    "over_flagging": evaluate_over_flagging_case,
    "control": evaluate_control_case,
}


async def evaluate_case(
    case: dict,
    scope: RetrievalScope,
    scope_id: UUID,
    supabase,
) -> dict:
    """Retrieve chunks for the case and dispatch to the per-type evaluator."""
    case_type = case.get("case_type")
    handler = _DISPATCH.get(case_type)
    if handler is None:
        return {
            "query": case.get("query"),
            "case_type": case_type,
            "status": "ERROR",
            "reason": f"unknown case_type: {case_type!r}",
        }

    chunks = await _retrieve_chunks(case["query"], scope, scope_id, supabase)
    return handler(case, chunks)


def aggregate_results(results: list[dict]) -> dict:
    """Build the per-case-type pass-rate summary."""
    by_type: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pass": 0, "fail": 0, "skip": 0, "error": 0}
    )
    for r in results:
        bucket = by_type[r.get("case_type") or "unknown"]
        bucket["total"] += 1
        status = r.get("status", "")
        if status == "PASS":
            bucket["pass"] += 1
        elif status == "FAIL":
            bucket["fail"] += 1
        elif status.startswith("SKIP"):
            bucket["skip"] += 1
        elif status == "ERROR":
            bucket["error"] += 1

    def pass_rate(b: dict[str, int]) -> Optional[float]:
        denom = b["total"] - b["skip"]
        return round(b["pass"] / denom, 4) if denom > 0 else None

    return {
        category: {**counts, "pass_rate": pass_rate(counts)}
        for category, counts in by_type.items()
    }


# ---------------------------------------------------------------------------
# Off-state byte-identical regression mode
# ---------------------------------------------------------------------------


def _collect_off_state_signature(results: list[dict]) -> dict[str, Any]:
    """Extract the regression signature from a results list.

    Signature shape:
        {
          "<query>": [[chunk_id, score], ...],
          ...
        }
    Only control-case queries are recorded — they are the fixed-query set
    the byte-identical regression watches.
    """
    return {
        r["query"]: r["retrieved_chunk_signature"]
        for r in results
        if r.get("case_type") == "control"
    }


def compare_signatures(
    baseline: dict[str, Any], current: dict[str, Any]
) -> list[str]:
    """Return a list of human-readable diff messages; empty list == identical."""
    diffs: list[str] = []
    baseline_keys = set(baseline.keys())
    current_keys = set(current.keys())
    for k in baseline_keys - current_keys:
        diffs.append(f"missing query in current: {k!r}")
    for k in current_keys - baseline_keys:
        diffs.append(f"unexpected query in current: {k!r}")
    for k in baseline_keys & current_keys:
        if baseline[k] != current[k]:
            diffs.append(
                f"signature changed for query {k!r}: "
                f"baseline={baseline[k]!r} current={current[k]!r}"
            )
    return diffs


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(aggregate: dict, results: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("RECENCY EVAL — RESULTS BY CASE TYPE")
    print("=" * 60)
    for category, counts in sorted(aggregate.items()):
        pr = counts["pass_rate"]
        pr_text = "n/a" if pr is None else f"{pr:.1%}"
        print(
            f"  {category:14s}  "
            f"pass={counts['pass']:>2d} / fail={counts['fail']:>2d} / "
            f"skip={counts['skip']:>2d} / err={counts['error']:>2d}  "
            f"(pass_rate {pr_text})"
        )

    fails = [r for r in results if r.get("status") == "FAIL"]
    if fails:
        print("\n--- FAILURES ---")
        for r in fails[:15]:
            print(f'  [{r["case_type"]}] "{r["query"][:65]}"')
            print(f'      {r.get("reason", "")}')
    skips = [r for r in results if r.get("status", "").startswith("SKIP")]
    if skips:
        print(f"\n  ({len(skips)} cases SKIPPED pending KIN-485 Component D)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def async_main() -> int:
    parser = argparse.ArgumentParser(
        description="Recency-aware eval runner (KIN-492)"
    )
    parser.add_argument("--dataset", required=True, help="Path to JSONL eval dataset")
    parser.add_argument(
        "--agent-slug",
        help="Agent slug — sets scope=agent_kb and resolves UUID",
    )
    parser.add_argument(
        "--scope",
        choices=["project_kb", "agent_kb"],
        help="Manual scope (if not using --agent-slug)",
    )
    parser.add_argument("--scope-id", help="Project or agent UUID")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: timestamped under evals/kb_retrieval/)",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument(
        "--supabase-key",
        default=(
            os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        ),
    )
    parser.add_argument(
        "--write-baseline",
        metavar="PATH",
        help="Capture the off-state byte-identical baseline to PATH and exit.",
    )
    parser.add_argument(
        "--regression-check",
        metavar="PATH",
        help="Compare current off-state output against the baseline at PATH; "
             "exit non-zero on any byte diff.",
    )
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        return 2

    cases = load_dataset(args.dataset)
    populated, offending = is_dataset_populated(cases)
    if not populated:
        print(
            f"Error: dataset {args.dataset!r} contains {len(offending)} "
            "unresolved placeholders (e.g. "
            f"{offending[0]!r}). Run populate_recency_dataset.py first.",
            file=sys.stderr,
        )
        return 2

    from supabase import create_client

    supabase = create_client(args.supabase_url, args.supabase_key)

    if args.agent_slug:
        scope = RetrievalScope.AGENT_KB
        scope_id = UUID(resolve_agent_id(supabase, args.agent_slug))
    elif args.scope and args.scope_id:
        scope = RetrievalScope(args.scope)
        scope_id = UUID(args.scope_id)
    else:
        print(
            "Error: provide --agent-slug or both --scope and --scope-id",
            file=sys.stderr,
        )
        return 2

    # In --write-baseline and --regression-check modes the off-state must be
    # frozen — force RECENCY_ENABLED off regardless of env. The runner only
    # cares about control cases for these modes, so other case_types are
    # excluded.
    if args.write_baseline or args.regression_check:
        from app.core import config

        original = config.settings.RECENCY_ENABLED
        config.settings.RECENCY_ENABLED = False
        try:
            control_cases = [c for c in cases if c.get("case_type") == "control"]
            results = [
                await evaluate_case(c, scope, scope_id, supabase)
                for c in control_cases
            ]
        finally:
            config.settings.RECENCY_ENABLED = original

        current_sig = _collect_off_state_signature(results)

        if args.write_baseline:
            with open(args.write_baseline, "w") as f:
                json.dump(current_sig, f, indent=2, sort_keys=True)
            print(f"Off-state baseline written to {args.write_baseline}")
            return 0

        with open(args.regression_check) as f:
            baseline_sig = json.load(f)
        diffs = compare_signatures(baseline_sig, current_sig)
        if diffs:
            print(
                "BYTE-IDENTICAL REGRESSION FAILED — "
                "RECENCY_ENABLED=False produced different output:",
                file=sys.stderr,
            )
            for d in diffs:
                print(f"  - {d}", file=sys.stderr)
            return 1
        print("Off-state byte-identical regression PASSED.")
        return 0

    # Standard mode — score every case.
    print(f"Loaded {len(cases)} cases from {args.dataset}", file=sys.stderr)
    results = []
    for i, case in enumerate(cases, 1):
        preview = (case.get("query") or "")[:60]
        print(f"  [{i}/{len(cases)}] {preview}...", file=sys.stderr, end="")
        try:
            results.append(await evaluate_case(case, scope, scope_id, supabase))
            status = results[-1].get("status", "?")
            print(f" {status}", file=sys.stderr)
        except Exception as e:
            print(f" ERROR: {e}", file=sys.stderr)
            results.append(
                {
                    "query": case.get("query"),
                    "case_type": case.get("case_type"),
                    "status": "ERROR",
                    "reason": str(e),
                }
            )

    aggregate = aggregate_results(results)
    print_report(aggregate, results)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or f"evals/kb_retrieval/recency_results_{ts}"
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scope": scope.value,
                "scope_id": str(scope_id),
                "dataset": args.dataset,
                "aggregate": aggregate,
                "per_case_results": results,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"Full results saved to {results_path}", file=sys.stderr)

    has_failures = any(r.get("status") == "FAIL" for r in results)
    return 1 if has_failures else 0


def main() -> None:
    sys.exit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
