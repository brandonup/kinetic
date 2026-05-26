"""
Framework selection eval runner (KIN-448).

Loads a JSONL eval dataset, runs select_framework() against live Supabase
with real embeddings, and computes precision@1, no-match accuracy, adjacent
FP rate, false negative rate, and MRR.

Usage:
    cd packages/api
    python -m evals.framework_selection.eval_runner \
        --dataset evals/framework_selection/dataset.jsonl \
        --agent-id <uuid> \
        --output-dir evals/framework_selection/results

Environment variables (or CLI overrides):
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY

Embedding uses the platform-owned Gemini key via `EmbeddingService()` (KIN-467).
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

# Add packages/api to path so app imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.rag.framework_selection import select_framework  # noqa: E402


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
    agent_id: str,
    supabase,
) -> list[dict]:
    """Run select_framework() for each eval case and collect results."""
    results: list[dict] = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        query_preview = case["query"][:60]
        print(f"  [{i}/{total}] {query_preview}...", file=sys.stderr, end="")

        try:
            match = await select_framework(
                query_text=case["query"],
                agent_id=agent_id,
                supabase=supabase,
            )

            actual_id = match.matched_framework_id
            expected_id = case["expected"]

            results.append({
                "query": case["query"],
                "expected": expected_id,
                "expected_name": case.get("expected_name"),
                "actual": actual_id,
                "actual_name": match.matched_framework_name,
                "score": match.confidence_score,
                "high_confidence": match.high_confidence,
                "label": case["label"],
                "adjacent_to": case.get("adjacent_to"),
                "adjacent_to_name": case.get("adjacent_to_name"),
                "source": case.get("source"),
                "correct": actual_id == expected_id,
            })

            status = "+" if actual_id == expected_id else "X"
            print(f" {status} (score={match.confidence_score:.3f})", file=sys.stderr)

        except Exception as e:
            print(f" ERROR: {e}", file=sys.stderr)
            results.append({
                "query": case["query"],
                "expected": case["expected"],
                "expected_name": case.get("expected_name"),
                "actual": None,
                "actual_name": None,
                "score": 0.0,
                "high_confidence": False,
                "label": case["label"],
                "correct": False,
                "error": str(e),
            })

    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results: list[dict]) -> dict:
    """Compute eval metrics from results."""
    on_topic = [r for r in results if r["label"] == "on-topic"]
    adjacent = [r for r in results if r["label"] == "adjacent"]
    off_topic = [r for r in results if r["label"] == "off-topic"]
    no_match_cases = adjacent + off_topic

    # Precision@1: correct matches / all on-topic (plan §4.2 pseudocode line 541)
    # Includes false negatives in denominator — conservative measure.
    on_topic_matched = [r for r in on_topic if r["actual"] is not None]
    precision_at_1 = (
        sum(1 for r in on_topic if r["correct"]) / len(on_topic)
        if on_topic
        else 0.0
    )

    # No-match accuracy: when no framework should fire, do we abstain?
    no_match_accuracy = (
        sum(1 for r in no_match_cases if r["actual"] is None) / len(no_match_cases)
        if no_match_cases
        else 0.0
    )

    # Adjacent FP rate: how often do adjacent queries trigger any framework?
    adjacent_fp_rate = (
        sum(1 for r in adjacent if r["actual"] is not None) / len(adjacent)
        if adjacent
        else 0.0
    )

    # False negative rate: how often do on-topic queries return no framework?
    false_negative_rate = (
        sum(1 for r in on_topic if r["actual"] is None) / len(on_topic)
        if on_topic
        else 0.0
    )

    # MRR deferred — select_framework() returns top-1 only. A proper MRR
    # requires the ranked candidate list, which the pipeline doesn't expose.
    # Will implement when the pipeline gains a top-N return mode.

    return {
        "precision_at_1": round(precision_at_1, 4),
        "no_match_accuracy": round(no_match_accuracy, 4),
        "adjacent_fp_rate": round(adjacent_fp_rate, 4),
        "false_negative_rate": round(false_negative_rate, 4),
        "counts": {
            "total": len(results),
            "on_topic": len(on_topic),
            "adjacent": len(adjacent),
            "off_topic": len(off_topic),
            "on_topic_matched": len(on_topic_matched),
            "on_topic_correct": sum(1 for r in on_topic if r["correct"]),
        },
        "launch_bars": {
            "precision_at_1": {"target": 0.80, "met": precision_at_1 >= 0.80},
            "no_match_accuracy": {"target": 0.85, "met": no_match_accuracy >= 0.85},
            "adjacent_fp_rate": {"target": 0.30, "met": adjacent_fp_rate <= 0.30},
            "false_negative_rate": {"target": 0.25, "met": false_negative_rate <= 0.25},
        },
    }


# ---------------------------------------------------------------------------
# Failure analysis
# ---------------------------------------------------------------------------

def failure_analysis(results: list[dict]) -> dict:
    """Analyze failure patterns by type and framework."""
    failures = [r for r in results if not r["correct"]]

    false_positives: list[dict] = []
    false_negatives: list[dict] = []
    wrong_framework: list[dict] = []

    for r in failures:
        if r["expected"] is None and r["actual"] is not None:
            false_positives.append(r)
        elif r["expected"] is not None and r["actual"] is None:
            false_negatives.append(r)
        elif r["expected"] is not None and r["actual"] is not None:
            wrong_framework.append(r)

    # Which frameworks cause the most false positives on adjacent queries?
    adjacent_fp_by_framework: dict[str, int] = defaultdict(int)
    for r in false_positives:
        if r.get("label") == "adjacent":
            name = r.get("actual_name") or r.get("actual") or "unknown"
            adjacent_fp_by_framework[name] += 1

    return {
        "total_failures": len(failures),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "wrong_framework": len(wrong_framework),
        "worst_fp_frameworks": dict(
            sorted(adjacent_fp_by_framework.items(), key=lambda x: -x[1])[:10]
        ),
        "failure_details": [
            {
                "query": r["query"],
                "expected": r.get("expected_name") or r["expected"],
                "actual": r.get("actual_name") or r["actual"],
                "score": r.get("score"),
                "label": r["label"],
            }
            for r in failures
        ],
    }


# ---------------------------------------------------------------------------
# Score distribution
# ---------------------------------------------------------------------------

def score_distribution(results: list[dict]) -> dict:
    """Compute similarity score stats for correct vs incorrect matches."""
    correct_scores = [r["score"] for r in results if r["correct"] and r["score"] > 0]
    incorrect_scores = [
        r["score"] for r in results if not r["correct"] and r["score"] > 0
    ]

    def stats(scores: list[float]) -> dict:
        if not scores:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0}
        s = sorted(scores)
        return {
            "count": len(s),
            "min": round(s[0], 4),
            "max": round(s[-1], 4),
            "mean": round(sum(s) / len(s), 4),
            "median": round(s[len(s) // 2], 4),
        }

    return {
        "correct_matches": stats(correct_scores),
        "incorrect_matches": stats(incorrect_scores),
        "all_scores_correct": correct_scores,
        "all_scores_incorrect": incorrect_scores,
    }


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------

def print_report(metrics: dict, failures: dict, distribution: dict):
    """Print human-readable eval report to stdout."""
    print("\n" + "=" * 60)
    print("FRAMEWORK SELECTION EVAL — BASELINE RESULTS")
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
        direction = (
            "<=" if name in ("adjacent_fp_rate", "false_negative_rate") else ">="
        )
        print(f"  [{symbol}] {name:25s} {value:6.1%}  (target {direction} {target:.0%})")

    print("\n  MRR: deferred (pipeline returns top-1 only)")

    print("\n--- Failure Analysis ---")
    print(f"  Total failures:   {failures['total_failures']}")
    print(f"  False positives:  {failures['false_positives']}")
    print(f"  False negatives:  {failures['false_negatives']}")
    print(f"  Wrong framework:  {failures['wrong_framework']}")

    if failures["worst_fp_frameworks"]:
        print("\n  Worst FP frameworks (adjacent queries):")
        for name, count in failures["worst_fp_frameworks"].items():
            print(f"    {count}x  {name}")

    print("\n--- Boosted Score Distribution ---")
    cor = distribution["correct_matches"]
    inc = distribution["incorrect_matches"]
    print(
        f"  Correct:    n={cor['count']}, mean={cor['mean']:.4f}, "
        f"median={cor['median']:.4f}, range=[{cor['min']:.4f}, {cor['max']:.4f}]"
    )
    print(
        f"  Incorrect:  n={inc['count']}, mean={inc['mean']:.4f}, "
        f"median={inc['median']:.4f}, range=[{inc['min']:.4f}, {inc['max']:.4f}]"
    )

    if failures["failure_details"]:
        print("\n--- Top Failures (first 15) ---")
        for f in failures["failure_details"][:15]:
            print(f'  FAIL: "{f["query"][:70]}"')
            print(
                f"        expected={f['expected']}, "
                f"got={f['actual']} (score={f['score']})"
            )

    print("\n" + "=" * 60)


def save_chart(distribution: dict, output_path: str):
    """Save score distribution chart (matplotlib) or CSV fallback."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))

        correct = distribution["all_scores_correct"]
        incorrect = distribution["all_scores_incorrect"]
        bins = [i * 0.05 for i in range(21)]  # 0.00 to 1.00

        if correct:
            ax.hist(
                correct,
                bins=bins,
                alpha=0.6,
                label=f"Correct (n={len(correct)})",
                color="green",
            )
        if incorrect:
            ax.hist(
                incorrect,
                bins=bins,
                alpha=0.6,
                label=f"Incorrect (n={len(incorrect)})",
                color="red",
            )

        ax.axvline(
            x=0.62, color="orange", linestyle="--", label="Confidence gate (0.62)"
        )
        ax.axvline(
            x=0.75, color="blue", linestyle="--", label="High confidence (0.75)"
        )

        ax.set_xlabel("Boosted Score (similarity + multi-trigger boost)")
        ax.set_ylabel("Count")
        ax.set_title("Framework Selection — Boosted Score Distribution (Correct vs Incorrect)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close()
        print(f"\nChart saved to {output_path}", file=sys.stderr)
    except ImportError:
        # Fallback: save raw data as CSV for external charting
        csv_path = output_path.replace(".png", ".csv")
        with open(csv_path, "w") as f:
            f.write("score,correct\n")
            for s in distribution["all_scores_correct"]:
                f.write(f"{s},true\n")
            for s in distribution["all_scores_incorrect"]:
                f.write(f"{s},false\n")
        print(
            f"\nmatplotlib not available — score data saved to {csv_path}",
            file=sys.stderr,
        )


def save_markdown_report(
    metrics: dict, failures: dict, distribution: dict, agent_id: str, dataset_path: str
) -> str:
    """Generate markdown report for docs/evals/."""
    from app.core.config import settings as _settings
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    c = metrics["counts"]

    lines = [
        "---",
        f"Date: {now}",
        "Ticket: KIN-448",
        f"Embedding model: {_settings.EMBEDDING_MODEL}",
        f"Agent: {agent_id}",
        f"Dataset: {dataset_path} ({c['total']} cases)",
        "---",
        "",
        "# L7 Framework Selection — Baseline Eval Results",
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
        direction = (
            "<=" if name in ("adjacent_fp_rate", "false_negative_rate") else ">="
        )
        status = "PASS" if met else "FAIL"
        lines.append(
            f"| {name} | {value:.1%} | {direction} {target:.0%} | {status} |"
        )

    lines.append(
        "| MRR (informational) | deferred | >= 0.7 | "
        "Pipeline returns top-1 only |"
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
            f"- **Total failures:** {failures['total_failures']}",
            f"- **False positives:** {failures['false_positives']} "
            f"(framework fired when it shouldn't)",
            f"- **False negatives:** {failures['false_negatives']} "
            f"(no framework when one should fire)",
            f"- **Wrong framework:** {failures['wrong_framework']} "
            f"(matched wrong framework)",
        ]
    )

    if failures["worst_fp_frameworks"]:
        lines.extend(["", "### Worst FP Frameworks (adjacent queries)", ""])
        for name, count in failures["worst_fp_frameworks"].items():
            lines.append(f"- {count}x — {name}")

    cor = distribution["correct_matches"]
    inc = distribution["incorrect_matches"]
    lines.extend(
        [
            "",
            "## Boosted Score Distribution",
            "",
            "| | Count | Mean | Median | Min | Max |",
            "|---|---|---|---|---|---|",
            f"| Correct | {cor['count']} | {cor['mean']:.4f} "
            f"| {cor['median']:.4f} | {cor['min']:.4f} | {cor['max']:.4f} |",
            f"| Incorrect | {inc['count']} | {inc['mean']:.4f} "
            f"| {inc['median']:.4f} | {inc['min']:.4f} | {inc['max']:.4f} |",
            "",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main():
    parser = argparse.ArgumentParser(
        description="Run framework selection eval (KIN-448)"
    )
    parser.add_argument(
        "--dataset", required=True, help="Path to JSONL eval dataset"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent-id", help="Agent definition UUID")
    group.add_argument(
        "--agent-slug",
        help="Agent slug (e.g., 'nate') — resolves UUID from DB",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: timestamped dir under evals/framework_selection/)",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
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

    # Resolve agent slug → UUID if needed
    agent_id = args.agent_id or resolve_agent_id(supabase, args.agent_slug)

    # Run eval
    print("\nRunning eval...", file=sys.stderr)
    results = await run_eval(cases, agent_id, supabase)

    # Compute
    metrics = compute_metrics(results)
    failures = failure_analysis(results)
    dist = score_distribution(results)

    # Print report
    print_report(metrics, failures, dist)

    # Save outputs
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or f"evals/framework_selection/results_{ts}"
    os.makedirs(output_dir, exist_ok=True)

    # JSON results (full detail)
    # `embedding_model` is recorded so cross-regime comparison is explicit
    # (KIN-467 migrated from OpenAI → Gemini; see KIN-497).
    from app.core.config import settings as _settings
    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "embedding_model": _settings.EMBEDDING_MODEL,
                "agent_id": agent_id,
                "dataset": args.dataset,
                "metrics": metrics,
                "failure_analysis": failures,
                "score_distribution": {
                    "correct_matches": dist["correct_matches"],
                    "incorrect_matches": dist["incorrect_matches"],
                },
                "per_case_results": results,
            },
            f,
            indent=2,
        )
    print(f"\nFull results saved to {results_path}", file=sys.stderr)

    # Chart
    chart_path = os.path.join(output_dir, "score_distribution.png")
    save_chart(dist, chart_path)

    # Markdown report for docs/evals/
    md = save_markdown_report(metrics, failures, dist, agent_id, args.dataset)
    md_path = os.path.join(output_dir, "baseline_report.md")
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Markdown report saved to {md_path}", file=sys.stderr)

    return metrics


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
