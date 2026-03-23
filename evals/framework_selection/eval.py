"""
Framework selection eval harness — KIN-260.

Runs the 4-step framework selection pipeline against the labeled dataset
and reports precision, recall, and false positive rate across a range of
cosine similarity thresholds.

Usage:
    python -m evals.framework_selection.eval --agent-id <uuid> [--threshold 0.65]

Prerequisites:
    1. A Kinetic API server running locally (KINETIC_API_URL env var, default http://localhost:8000)
    2. A valid user JWT (KINETIC_JWT env var)
    3. An agent pre-loaded with SEED_FRAMEWORKS (run seed_agent() below or create manually)

Output:
    - Per-case results (query, expected, got, correct)
    - Per-threshold metrics table
    - Threshold recommendation

Results are saved to evals/framework_selection/results/YYYY-MM-DD-HH-MM.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from .cases import EVAL_CASES, SEED_FRAMEWORKS, EvalCase

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("KINETIC_API_URL", "http://localhost:8000")
JWT = os.environ.get("KINETIC_JWT", "")

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

THRESHOLDS_TO_SWEEP = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


# ---------------------------------------------------------------------------
# API client helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    if not JWT:
        raise RuntimeError(
            "Set KINETIC_JWT env var to a valid user JWT before running evals."
        )
    return {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}


def seed_agent(name: str = "Eval Agent") -> str:
    """
    Create a new private agent and upload SEED_FRAMEWORKS to it.
    Returns the agent_id. Idempotent by name — if an agent with this name
    already exists, returns its id.
    """
    client = httpx.Client(base_url=API_BASE, headers=_headers(), timeout=60)

    # Check for existing agent
    resp = client.get("/api/v1/agents")
    resp.raise_for_status()
    for ag in resp.json().get("agents", []):
        if ag["name"] == name and ag["owner_id"] == _current_user_id(client):
            print(f"Reusing existing eval agent: {ag['id']}")
            return ag["id"]

    # Create agent
    resp = client.post(
        "/api/v1/agents",
        json={
            "name": name,
            "instructions": "Eval agent — do not invoke in production.",
            "type": "custom",
            "visibility": "private",
        },
    )
    resp.raise_for_status()
    agent_id = resp.json()["id"]
    print(f"Created eval agent: {agent_id}")

    # Upload frameworks one by one
    for fw in SEED_FRAMEWORKS:
        resp = client.post(f"/api/v1/agents/{agent_id}/frameworks", json=fw)
        if resp.status_code not in (200, 201):
            print(f"  Warning: framework '{fw['framework_id']}' upload failed: {resp.text}")
        else:
            print(f"  Seeded: {fw['framework_id']}")

    return agent_id


def _current_user_id(client: httpx.Client) -> str:
    resp = client.get("/api/v1/profile")
    resp.raise_for_status()
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Pipeline call
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    selected_framework_id: Optional[str]
    similarity_score: Optional[float]
    reranker_score: Optional[float]
    all_candidates: list[dict]  # [{framework_id, similarity_score, reranker_score}]


def run_pipeline(
    agent_id: str,
    query: str,
    threshold: float,
    client: httpx.Client,
) -> PipelineResult:
    """
    Call the framework selection pipeline endpoint.

    Expected endpoint: POST /api/v1/agents/{agent_id}/frameworks/select
    Body: { "query": str, "threshold": float }
    Response:
      {
        "selected_framework_id": "uuid | null",
        "similarity_score": float | null,
        "reranker_score": float | null,
        "candidates": [{"framework_id": str, "similarity_score": float, "reranker_score": float | null}]
      }

    NOTE: This endpoint is defined as part of Sprint 4 (Big Head KIN-290).
    If not yet implemented, this function raises NotImplementedError.
    The eval harness gracefully handles NotImplementedError by marking
    all cases as "pending" and skipping metric calculation.
    """
    resp = client.post(
        f"/api/v1/agents/{agent_id}/frameworks/select",
        json={"query": query, "threshold": threshold},
    )
    if resp.status_code == 404:
        raise NotImplementedError(
            "Framework selection endpoint not yet implemented (Sprint 4 KIN-290). "
            "Run this eval after Big Head ships the pipeline."
        )
    resp.raise_for_status()
    data = resp.json()
    return PipelineResult(
        selected_framework_id=data.get("selected_framework_id"),
        similarity_score=data.get("similarity_score"),
        reranker_score=data.get("reranker_score"),
        all_candidates=data.get("candidates", []),
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    query: str
    category: str
    expected_framework_ids: list[str]
    selected_framework_id: Optional[str]
    correct: bool
    result_type: str  # "TP", "TN", "FP", "FN", "ambiguous_correct", "ambiguous_incorrect"
    notes: str


def score_case(case: EvalCase, pipeline_result: PipelineResult) -> CaseResult:
    selected = pipeline_result.selected_framework_id
    expected = case.expected_framework_ids

    if case.category == "no_match":
        if selected is None:
            rtype, correct = "TN", True
        else:
            rtype, correct = "FP", False
    elif case.category in ("clear_match", "multi_turn"):
        if not expected:
            # multi_turn with no expected match
            if selected is None:
                rtype, correct = "TN", True
            else:
                rtype, correct = "FP", False
        else:
            target = expected[0]
            if selected == target:
                rtype, correct = "TP", True
            elif selected is None:
                rtype, correct = "FN", False
            else:
                rtype, correct = "FP", False
    elif case.category == "ambiguous":
        if selected in expected:
            rtype, correct = "ambiguous_correct", True
        elif selected is None:
            # Debatable — ambiguous with no selection is conservative, not wrong
            rtype, correct = "FN", False
        else:
            rtype, correct = "ambiguous_incorrect", False
    else:
        rtype, correct = "unknown", False

    return CaseResult(
        query=case.query,
        category=case.category,
        expected_framework_ids=expected,
        selected_framework_id=selected,
        correct=correct,
        result_type=rtype,
        notes=case.notes,
    )


@dataclass
class ThresholdMetrics:
    threshold: float
    precision: float  # TP / (TP + FP)
    recall: float     # TP / (TP + FN)
    false_positive_rate: float  # FP / (FP + TN)
    f1: float
    n_cases: int
    n_tp: int
    n_tn: int
    n_fp: int
    n_fn: int


def compute_metrics(results: list[CaseResult], threshold: float) -> ThresholdMetrics:
    tp = sum(1 for r in results if r.result_type in ("TP", "ambiguous_correct"))
    tn = sum(1 for r in results if r.result_type == "TN")
    fp = sum(1 for r in results if r.result_type in ("FP", "ambiguous_incorrect"))
    fn = sum(1 for r in results if r.result_type == "FN")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return ThresholdMetrics(
        threshold=threshold,
        precision=precision,
        recall=recall,
        false_positive_rate=fpr,
        f1=f1,
        n_cases=len(results),
        n_tp=tp,
        n_tn=tn,
        n_fp=fp,
        n_fn=fn,
    )


def recommend_threshold(metrics_by_threshold: list[ThresholdMetrics]) -> ThresholdMetrics:
    """
    Selection criteria (in priority order):
      1. False positive rate < 0.10 (wrong injection actively undermines trust)
      2. Precision ≥ 0.85 (when it fires, it should be right)
      3. Highest F1 among qualifying thresholds

    If no threshold meets criteria 1+2, return the one with lowest FPR.
    """
    candidates = [
        m for m in metrics_by_threshold
        if m.false_positive_rate < 0.10 and m.precision >= 0.85
    ]
    if candidates:
        return max(candidates, key=lambda m: m.f1)
    # Fallback: lowest false positive rate
    return min(metrics_by_threshold, key=lambda m: m.false_positive_rate)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(
    all_results: dict[float, list[CaseResult]],
    metrics: list[ThresholdMetrics],
    recommended: ThresholdMetrics,
) -> None:
    print("\n" + "=" * 70)
    print("FRAMEWORK SELECTION EVAL — THRESHOLD SWEEP")
    print("=" * 70)

    print(f"\n{'Threshold':>12}  {'Precision':>10}  {'Recall':>8}  {'FPR':>8}  {'F1':>8}  {'TP/TN/FP/FN'}")
    print("-" * 70)
    for m in metrics:
        marker = " ← RECOMMENDED" if m.threshold == recommended.threshold else ""
        print(
            f"{m.threshold:>12.2f}  {m.precision:>10.3f}  {m.recall:>8.3f}  "
            f"{m.false_positive_rate:>8.3f}  {m.f1:>8.3f}  "
            f"{m.n_tp}/{m.n_tn}/{m.n_fp}/{m.n_fn}{marker}"
        )

    print(f"\nRECOMMENDED THRESHOLD: {recommended.threshold}")
    print(
        f"  Precision={recommended.precision:.3f}  Recall={recommended.recall:.3f}  "
        f"FPR={recommended.false_positive_rate:.3f}  F1={recommended.f1:.3f}"
    )

    # Show failures at recommended threshold
    failures = [r for r in all_results[recommended.threshold] if not r.correct]
    if failures:
        print(f"\nFAILURES at threshold={recommended.threshold} ({len(failures)} cases):")
        for r in failures:
            print(f"  [{r.result_type}] [{r.category}] {r.query[:70]!r}")
            print(f"    expected={r.expected_framework_ids}  got={r.selected_framework_id!r}")


def save_results(
    agent_id: str,
    all_results: dict[float, list[CaseResult]],
    metrics: list[ThresholdMetrics],
    recommended: ThresholdMetrics,
) -> Path:
    ts = datetime.utcnow().strftime("%Y-%m-%d-%H-%M")
    out_path = RESULTS_DIR / f"{ts}-threshold-sweep.json"
    payload = {
        "run_at": datetime.utcnow().isoformat(),
        "agent_id": agent_id,
        "recommended_threshold": recommended.threshold,
        "metrics": [asdict(m) for m in metrics],
        "cases_by_threshold": {
            str(t): [asdict(r) for r in results]
            for t, results in all_results.items()
        },
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults saved: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_eval(agent_id: str, thresholds: list[float]) -> None:
    client = httpx.Client(base_url=API_BASE, headers=_headers(), timeout=60)

    all_results: dict[float, list[CaseResult]] = {}
    metrics_list: list[ThresholdMetrics] = []

    try:
        for threshold in thresholds:
            print(f"\nRunning threshold={threshold:.2f} ...")
            case_results: list[CaseResult] = []
            for case in EVAL_CASES:
                try:
                    pipeline_result = run_pipeline(agent_id, case.query, threshold, client)
                    result = score_case(case, pipeline_result)
                except NotImplementedError as e:
                    print(f"\n⚠️  {e}")
                    print("Eval cannot run until Sprint 4 KIN-290 ships.")
                    sys.exit(1)
                case_results.append(result)
                marker = "✓" if result.correct else "✗"
                print(f"  {marker} [{result.category:12}] {result.query[:55]!r}")

            all_results[threshold] = case_results
            metrics_list.append(compute_metrics(case_results, threshold))

    finally:
        client.close()

    recommended = recommend_threshold(metrics_list)
    print_report(all_results, metrics_list, recommended)
    save_results(agent_id, all_results, metrics_list, recommended)


def main() -> None:
    parser = argparse.ArgumentParser(description="Framework selection threshold eval")
    parser.add_argument("--agent-id", required=False, help="Existing eval agent UUID")
    parser.add_argument("--seed", action="store_true", help="Create and seed eval agent, then run")
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Run at a single threshold instead of sweeping",
    )
    args = parser.parse_args()

    if args.seed:
        agent_id = seed_agent()
    elif args.agent_id:
        agent_id = args.agent_id
    else:
        parser.error("Provide --agent-id or use --seed to create a fresh eval agent")

    thresholds = [args.threshold] if args.threshold else THRESHOLDS_TO_SWEEP
    run_eval(agent_id, thresholds)


if __name__ == "__main__":
    main()
