"""
KB retrieval eval runner (KIN-449).

Loads a JSONL eval dataset, runs retrieve() against live Supabase with real
embeddings, and computes Precision@8, Recall@20, MRR, and false injection rate.

Usage:
    cd packages/api
    python -m evals.kb_retrieval.eval_runner \
        --dataset evals/kb_retrieval/dataset.jsonl \
        --scope agent_kb --scope-id <agent-uuid>

Environment variables (or CLI overrides):
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY

Embedding uses the platform-owned Gemini key via `EmbeddingService()` (KIN-467).
No OpenAI key is required.
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

# Add packages/api to path so app imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.rag.retrieval import (  # noqa: E402
    RetrievalScope,
    retrieve,
)


# ---------------------------------------------------------------------------
# Agent slug → UUID resolution
# ---------------------------------------------------------------------------

def resolve_agent_id(supabase, slug: str) -> str:
    """Look up agent_definition UUID from slug."""
    result = (
        supabase.table("agent_definitions")
        .select("id, name, slug")
        .eq("slug", slug)
        .execute()
    )
    agents = result.data or []
    if not agents:
        all_agents = (
            supabase.table("agent_definitions")
            .select("id, name, slug")
            .execute()
        )
        available = all_agents.data or []
        print(f"Error: No agent found with slug '{slug}'", file=sys.stderr)
        if available:
            print("Available agents in this database:", file=sys.stderr)
            for a in available:
                print(
                    f"  - {a.get('name', '?')} (slug: '{a.get('slug', '')}', "
                    f"id: {a['id']})",
                    file=sys.stderr,
                )
        else:
            print(
                "No agents exist in this database. Are you pointing at the "
                "right Supabase instance?",
                file=sys.stderr,
            )
        sys.exit(1)
    agent = agents[0]
    print(
        f"Resolved agent '{slug}' → {agent['name']} ({agent['id']})",
        file=sys.stderr,
    )
    return agent["id"]


# ---------------------------------------------------------------------------
# Eval execution
# ---------------------------------------------------------------------------

async def run_eval(
    cases: list[dict],
    scope: RetrievalScope,
    scope_id: UUID,
    supabase,
    similarity_threshold: float = 0.3,
) -> list[dict]:
    """Run retrieve() for each eval case and collect results."""
    results: list[dict] = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        query_preview = case["query"][:60]
        print(f"  [{i}/{total}] {query_preview}...", file=sys.stderr, end="")

        try:
            # Use mmr_top_k=20 to get full candidate set for Recall@20.
            # similarity_threshold defaults to production value (0.3) so
            # false injection rate reflects real-world behavior. Use
            # --no-threshold to disable for raw pipeline analysis.
            chunks = await retrieve(
                query_text=case["query"],
                scope=scope,
                scope_id=scope_id,
                supabase=supabase,
                model_context_window=1_000_000,
                vector_top_k=20,
                mmr_top_k=20,
                similarity_threshold=similarity_threshold,
            )

            retrieved_doc_ids = [c.document_id for c in chunks]
            retrieved_top8_doc_ids = [c.document_id for c in chunks[:8]]
            should_retrieve = set(case.get("should_retrieve") or [])
            should_not_retrieve = set(case.get("should_not_retrieve") or [])

            # Precision@8 — KIN-497: redefined as DOCUMENT-LEVEL (was chunk-level).
            # The chunk-level definition penalises retrieval for finding the right
            # doc *and* other topically-relevant docs — which is exactly what we want
            # on a dense corpus like Nate's (567 AI-commentary articles, many
            # overlapping topics). Doc-level precision answers the question users
            # actually care about: did the target doc appear in the top-8?
            #
            # `precision_at_8_chunks` keeps the legacy chunk-level computation
            # for info-only diagnostics (high chunk-level FIR can still flag
            # noisy injection even when the right doc is present).
            top8_doc_set = set(retrieved_top8_doc_ids)
            if chunks[:8]:
                # Doc-level: fraction of should_retrieve docs present in top-8 doc-set.
                if should_retrieve:
                    precision_at_8 = (
                        len(should_retrieve & top8_doc_set) / len(should_retrieve)
                    )
                else:
                    # No docs expected → precision is 1.0 if nothing came back, 0 otherwise.
                    precision_at_8 = 0.0
                # Legacy chunk-level for diagnostics.
                relevant_chunks_in_top8 = sum(
                    1 for did in retrieved_top8_doc_ids if did in should_retrieve
                )
                precision_at_8_chunks = relevant_chunks_in_top8 / len(chunks[:8])
            else:
                precision_at_8 = 1.0 if not should_retrieve else 0.0
                precision_at_8_chunks = precision_at_8

            # Recall@20: fraction of relevant docs with >= 1 chunk in all results
            if should_retrieve:
                retrieved_relevant_docs = should_retrieve & set(retrieved_doc_ids)
                recall_at_20 = len(retrieved_relevant_docs) / len(should_retrieve)
            else:
                recall_at_20 = 1.0  # No docs to retrieve = perfect recall

            # MRR: 1/rank of first relevant chunk
            mrr = 0.0
            for rank, chunk in enumerate(chunks, 1):
                if chunk.document_id in should_retrieve:
                    mrr = 1.0 / rank
                    break

            # False injection: fraction of top-8 from irrelevant documents.
            # For off-topic/adjacent cases with empty should_not_retrieve,
            # ALL returned chunks are false injections (nothing should match).
            if chunks[:8]:
                if should_not_retrieve:
                    false_injections = sum(
                        1 for did in retrieved_top8_doc_ids
                        if did in should_not_retrieve
                    )
                elif not should_retrieve:
                    # No docs should be retrieved — everything returned is false
                    false_injections = len(chunks[:8])
                else:
                    # On-topic: count chunks NOT from should_retrieve
                    false_injections = sum(
                        1 for did in retrieved_top8_doc_ids
                        if did not in should_retrieve
                    )
                false_injection_rate = false_injections / len(chunks[:8])
            else:
                false_injection_rate = 0.0

            results.append({
                "query": case["query"],
                "label": case["label"],
                "should_retrieve": list(should_retrieve),
                "should_not_retrieve": list(should_not_retrieve),
                "retrieved_doc_ids_top8": retrieved_top8_doc_ids,
                "retrieved_doc_ids_all": retrieved_doc_ids,
                "num_chunks_returned": len(chunks),
                "top_scores": [round(c.similarity_score, 4) for c in chunks[:8]],
                "precision_at_8": round(precision_at_8, 4),
                "precision_at_8_chunks": round(precision_at_8_chunks, 4),
                "recall_at_20": round(recall_at_20, 4),
                "mrr": round(mrr, 4),
                "false_injection_rate": round(false_injection_rate, 4),
            })

            status = "+" if precision_at_8 >= 0.5 else "X"
            n_chunks = len(chunks)
            top_score = chunks[0].similarity_score if chunks else 0.0
            print(
                f" {status} ({n_chunks} chunks, top={top_score:.3f}, "
                f"p@8={precision_at_8:.2f})",
                file=sys.stderr,
            )

        except Exception as e:
            print(f" ERROR: {e}", file=sys.stderr)
            results.append({
                "query": case["query"],
                "label": case["label"],
                "error": str(e),
                "precision_at_8": 0.0,
                "precision_at_8_chunks": 0.0,
                "recall_at_20": 0.0,
                "mrr": 0.0,
                "false_injection_rate": 0.0,
            })

    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results: list[dict]) -> dict:
    """Compute aggregate eval metrics from per-case results."""
    on_topic = [r for r in results if r["label"] == "on-topic"]
    adjacent = [r for r in results if r["label"] == "adjacent"]
    off_topic = [r for r in results if r["label"] == "off-topic"]

    def safe_mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    # Aggregate metrics over on-topic cases (the primary eval set)
    precision_at_8 = safe_mean([r["precision_at_8"] for r in on_topic])
    precision_at_8_chunks = safe_mean(
        [r.get("precision_at_8_chunks", 0.0) for r in on_topic]
    )
    recall_at_20 = safe_mean([r["recall_at_20"] for r in on_topic])
    mrr = safe_mean([r["mrr"] for r in on_topic])

    # False injection rate across adjacent + off-topic cases
    no_match_cases = adjacent + off_topic
    false_injection_rate = safe_mean(
        [r["false_injection_rate"] for r in no_match_cases]
    ) if no_match_cases else 0.0

    # Also compute: how often do off-topic/adjacent queries return ANY chunks?
    false_fire_rate = (
        sum(1 for r in no_match_cases if r.get("num_chunks_returned", 0) > 0)
        / len(no_match_cases)
        if no_match_cases
        else 0.0
    )

    return {
        "precision_at_8": round(precision_at_8, 4),
        "precision_at_8_chunks": round(precision_at_8_chunks, 4),
        "recall_at_20": round(recall_at_20, 4),
        "mrr": round(mrr, 4),
        "false_injection_rate": round(false_injection_rate, 4),
        "false_fire_rate": round(false_fire_rate, 4),
        "counts": {
            "total": len(results),
            "on_topic": len(on_topic),
            "adjacent": len(adjacent),
            "off_topic": len(off_topic),
        },
        "launch_bars": {
            "precision_at_8": {"target": 0.70, "met": precision_at_8 >= 0.70},
            "recall_at_20": {"target": 0.80, "met": recall_at_20 >= 0.80},
            "mrr": {"target": 0.60, "met": mrr >= 0.60},
            "false_injection_rate": {
                "target": 0.15,
                "met": false_injection_rate <= 0.15,
            },
        },
    }


# ---------------------------------------------------------------------------
# Failure analysis
# ---------------------------------------------------------------------------

def failure_analysis(results: list[dict]) -> dict:
    """Analyze retrieval failure patterns."""
    # On-topic failures: low precision or recall
    on_topic = [r for r in results if r["label"] == "on-topic"]
    low_precision = [r for r in on_topic if r["precision_at_8"] < 0.5]
    low_recall = [r for r in on_topic if r["recall_at_20"] < 0.5]
    zero_recall = [r for r in on_topic if r["recall_at_20"] == 0.0]

    # Adjacent/off-topic false fires
    no_match = [r for r in results if r["label"] in ("adjacent", "off-topic")]
    false_fires = [r for r in no_match if r.get("num_chunks_returned", 0) > 0]

    # Which documents are most commonly falsely injected?
    false_doc_counts: dict[str, int] = defaultdict(int)
    for r in false_fires:
        for doc_id in r.get("retrieved_doc_ids_top8", []):
            false_doc_counts[doc_id] += 1

    return {
        "low_precision_count": len(low_precision),
        "low_recall_count": len(low_recall),
        "zero_recall_count": len(zero_recall),
        "false_fire_count": len(false_fires),
        "worst_false_injection_docs": dict(
            sorted(false_doc_counts.items(), key=lambda x: -x[1])[:10]
        ),
        "failure_details": [
            {
                "query": r["query"],
                "label": r["label"],
                "precision_at_8": r["precision_at_8"],
                "recall_at_20": r["recall_at_20"],
                "num_chunks": r.get("num_chunks_returned", 0),
                "top_scores": r.get("top_scores", []),
            }
            for r in (low_precision + low_recall + false_fires)[:20]
        ],
    }


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------

def print_report(metrics: dict, failures: dict):
    """Print human-readable eval report to stdout."""
    print("\n" + "=" * 60)
    print("KB RETRIEVAL EVAL — BASELINE RESULTS")
    print("=" * 60)

    c = metrics["counts"]
    print(
        f"\nDataset: {c['total']} cases "
        f"({c['on_topic']} on-topic, {c['adjacent']} adjacent, "
        f"{c['off_topic']} off-topic)"
    )

    print("\n--- Metrics vs Launch Bars ---")
    for name, bar in metrics["launch_bars"].items():
        value = metrics[name]
        target = bar["target"]
        met = bar["met"]
        symbol = "PASS" if met else "FAIL"
        direction = "<=" if name == "false_injection_rate" else ">="
        print(
            f"  [{symbol}] {name:25s} {value:6.1%}  (target {direction} {target:.0%})"
        )

    print(f"\n  False fire rate (info):    {metrics['false_fire_rate']:.1%}")
    print(
        f"  Chunk-level p@8 (info):    {metrics.get('precision_at_8_chunks', 0):.1%}  "
        f"(legacy chunk-level metric; primary p@8 is now doc-level — KIN-497)"
    )

    print("\n--- Failure Analysis ---")
    print(f"  Low precision (<50%):  {failures['low_precision_count']}")
    print(f"  Low recall (<50%):     {failures['low_recall_count']}")
    print(f"  Zero recall:           {failures['zero_recall_count']}")
    print(f"  False fires:           {failures['false_fire_count']}")

    if failures["failure_details"]:
        print("\n--- Top Failures (first 15) ---")
        for f in failures["failure_details"][:15]:
            scores_str = (
                ", ".join(f"{s:.3f}" for s in f["top_scores"][:3])
                if f["top_scores"]
                else "none"
            )
            print(f'  [{f["label"]}] "{f["query"][:60]}"')
            print(
                f"         p@8={f['precision_at_8']:.2f}, "
                f"r@20={f['recall_at_20']:.2f}, "
                f"chunks={f['num_chunks']}, "
                f"scores=[{scores_str}]"
            )

    print("\n" + "=" * 60)


def save_markdown_report(
    metrics: dict,
    failures: dict,
    scope: str,
    scope_id: str,
    dataset_path: str,
) -> str:
    """Generate markdown report for docs/evals/."""
    from app.core.config import settings as _settings
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    c = metrics["counts"]

    lines = [
        "---",
        f"Date: {now}",
        "Ticket: KIN-449",
        f"Embedding model: {_settings.EMBEDDING_MODEL}",
        f"Scope: {scope} ({scope_id})",
        f"Dataset: {dataset_path} ({c['total']} cases)",
        "---",
        "",
        "# L8/L9 KB Retrieval — Baseline Eval Results",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Target | Status |",
        "|--------|-------|--------|--------|",
    ]

    for name, bar in metrics["launch_bars"].items():
        value = metrics[name]
        target = bar["target"]
        met = bar["met"]
        direction = "<=" if name == "false_injection_rate" else ">="
        status = "PASS" if met else "FAIL"
        lines.append(
            f"| {name} | {value:.1%} | {direction} {target:.0%} | {status} |"
        )

    lines.append(
        f"| false_fire_rate (info) | {metrics['false_fire_rate']:.1%} | — | — |"
    )

    lines.extend(
        [
            "",
            "## Dataset Breakdown",
            "",
            f"- **Total:** {c['total']} cases",
            f"- **On-topic:** {c['on_topic']}",
            f"- **Adjacent:** {c['adjacent']}",
            f"- **Off-topic:** {c['off_topic']}",
            "",
            "## Failure Analysis",
            "",
            f"- **Low precision (<50%):** {failures['low_precision_count']}",
            f"- **Low recall (<50%):** {failures['low_recall_count']}",
            f"- **Zero recall:** {failures['zero_recall_count']}",
            f"- **False fires:** {failures['false_fire_count']}",
        ]
    )

    if failures["worst_false_injection_docs"]:
        lines.extend(["", "### Most Frequently Falsely Injected Documents", ""])
        for doc_id, count in failures["worst_false_injection_docs"].items():
            lines.append(f"- {count}x — `{doc_id}`")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main():
    parser = argparse.ArgumentParser(
        description="Run KB retrieval eval (KIN-449)"
    )
    parser.add_argument(
        "--dataset", required=True, help="Path to JSONL eval dataset"
    )
    parser.add_argument(
        "--scope",
        choices=["project_kb", "agent_kb"],
        help="Retrieval scope",
    )
    parser.add_argument("--scope-id", help="Project or agent UUID")
    parser.add_argument(
        "--agent-slug",
        help="Agent slug (e.g., 'nate') — sets scope=agent_kb and resolves UUID",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: timestamped dir)",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    parser.add_argument(
        "--no-threshold",
        action="store_true",
        help="Disable similarity threshold (raw pipeline output, inflates false injection rate)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override similarity threshold (e.g. 0.45). Defaults to the prod "
             "settings.SIMILARITY_THRESHOLD. Use this for sweeping (KIN-497).",
    )
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)

    # Load dataset
    with open(args.dataset) as f:
        cases = [json.loads(line) for line in f if line.strip()]
    print(f"Loaded {len(cases)} eval cases from {args.dataset}", file=sys.stderr)

    # Connect
    from supabase import create_client

    supabase = create_client(args.supabase_url, args.supabase_key)

    # Resolve agent slug → scope + scope_id
    if args.agent_slug:
        scope = RetrievalScope.AGENT_KB
        scope_id = UUID(resolve_agent_id(supabase, args.agent_slug))
    elif args.scope and args.scope_id:
        scope = RetrievalScope(args.scope)
        scope_id = UUID(args.scope_id)
    else:
        print(
            "Error: Provide either --agent-slug or both --scope and --scope-id",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run eval
    if args.no_threshold:
        threshold = 0.0
        mode = "raw (no threshold)"
    elif args.threshold is not None:
        threshold = args.threshold
        mode = f"sweep (threshold={threshold})"
    else:
        from app.core.config import settings as _settings
        threshold = _settings.SIMILARITY_THRESHOLD
        mode = f"production (threshold={threshold})"
    print(f"\nRunning eval in {mode} mode...", file=sys.stderr)
    results = await run_eval(
        cases, scope, scope_id, supabase,
        similarity_threshold=threshold,
    )

    # Compute
    metrics = compute_metrics(results)
    failures = failure_analysis(results)

    # Print report
    print_report(metrics, failures)

    # Save outputs
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or f"evals/kb_retrieval/results_{ts}"
    os.makedirs(output_dir, exist_ok=True)

    # JSON results
    # `embedding_model` is recorded so cross-regime comparison is explicit
    # (KIN-467 migrated from OpenAI → Gemini; see KIN-497).
    from app.core.config import settings as _settings
    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "embedding_model": _settings.EMBEDDING_MODEL,
                "scope": scope.value,
                "scope_id": str(scope_id),
                "dataset": args.dataset,
                "metrics": metrics,
                "failure_analysis": failures,
                "per_case_results": results,
            },
            f,
            indent=2,
        )
    print(f"\nFull results saved to {results_path}", file=sys.stderr)

    # Markdown report
    md = save_markdown_report(
        metrics, failures, scope.value, str(scope_id), args.dataset
    )
    md_path = os.path.join(output_dir, "baseline_report.md")
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Markdown report saved to {md_path}", file=sys.stderr)

    return metrics


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
