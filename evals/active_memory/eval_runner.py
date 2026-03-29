"""
Active Memory proposal quality eval runner — KIN-328.

Tests whether the PROPOSAL_PROMPT generates meaningful, durable facts from conversations.

Usage:
    cd projects/kinetic
    OPENAI_API_KEY=sk-... python evals/active_memory/eval_runner.py

    # Or with a specific judge model:
    OPENAI_API_KEY=sk-... JUDGE_MODEL=gpt-4o python evals/active_memory/eval_runner.py

    # Dry-run (skip LLM calls, use mock proposals for framework validation):
    DRY_RUN=1 python evals/active_memory/eval_runner.py

Requirements:
    - OPENAI_API_KEY env var (or set JUDGE_API_KEY separately for judge vs generation)
    - packages/api/requirements.txt installed in environment

Pass criteria:
    - Mean proposal score ≥ 1.5 across all proposals from all conversations
    - Edge cases: sparse/task conversations generate ≤ 2 proposals
    - No hallucinated content (score=0 proposals < 15% of total)

Exit codes:
    0 = PASS
    1 = FAIL (below threshold)
    2 = ERROR (configuration or execution failure)
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — import app modules from packages/api
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_ROOT = PROJECT_ROOT / "packages" / "api"
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from evals.active_memory.conversations import CONVERSATIONS
from evals.active_memory.judge import judge_conversation

# ---------------------------------------------------------------------------
# Inline proposal generation (calls the same logic as _generate_proposals_job)
# without needing a running FastAPI server or DB connection.
# ---------------------------------------------------------------------------

PROPOSAL_PROMPT = (
    "Review this conversation and identify 1–5 facts, decisions, preferences, or working patterns "
    "worth remembering in future sessions. Each entry should be a short, standalone sentence. "
    "Focus on things that would change how an AI collaborates with this person — not summaries "
    "of what was discussed.\n"
    "Format: return a JSON array of strings. Maximum 5 items. "
    "If nothing worth remembering, return []."
)


def _parse_proposals(text: str) -> list:
    try:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [str(item) for item in data if isinstance(item, str) and item.strip()]
    except Exception:
        pass
    return []


def generate_proposals(messages: list, api_key: str, model: str = "gpt-4o-mini") -> list:
    """
    Run the proposal generation prompt against a conversation, mimicking
    the logic in _generate_proposals_job (conversations.py).
    """
    from app.services.llm_client import call_llm

    chat_messages = list(messages) + [{"role": "user", "content": PROPOSAL_PROMPT}]
    response = call_llm(
        messages=chat_messages,
        model=model,
        api_key=api_key,
        max_tokens=400,
        timeout=30,
    )
    return _parse_proposals(response)


def dry_run_proposals(messages: list) -> list:
    """
    Mock proposal generation for dry-run mode.
    Returns 1-3 plausible proposals based on conversation length.
    """
    n = len(messages)
    if n <= 2:
        return ["User uses Cursor IDE as their primary development environment."]
    if n <= 4:
        return [
            "User prefers to work in deep-focus blocks without interruptions.",
            "User values async collaboration over synchronous meetings.",
        ]
    return [
        "User has strong opinions about code architecture — prefers thin controllers with business logic in services.",
        "User never catches broad exceptions and considers silent failure a serious code smell.",
        "User requires 80% test coverage minimum on all code before merging.",
    ]


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_eval():
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("JUDGE_API_KEY")
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-4o")
    gen_model = os.environ.get("GEN_MODEL", "gpt-4o-mini")
    dry_run = os.environ.get("DRY_RUN", "0") == "1"

    if not dry_run and not api_key:
        print("ERROR: Set OPENAI_API_KEY or JUDGE_API_KEY to run this eval.", file=sys.stderr)
        sys.exit(2)

    print(f"{'[DRY RUN] ' if dry_run else ''}Active Memory proposal quality eval — {len(CONVERSATIONS)} conversations")
    print(f"  Generation model: {gen_model}  |  Judge model: {judge_model}\n")

    results = []
    all_proposals_scored = []

    for conv in CONVERSATIONS:
        print(f"  [{conv['id']}] {conv['label']} ({conv['category']}) ...", end=" ", flush=True)

        if dry_run:
            proposals = dry_run_proposals(conv["messages"])
        else:
            proposals = generate_proposals(conv["messages"], api_key, gen_model)

        if dry_run:
            # Assign mock scores for framework validation
            scored_proposals = [{"proposal": p, "score": 2, "reason": "dry-run mock"} for p in proposals]
            mean = 2.0 if proposals else None
            result = {
                "conversation_id": conv["id"],
                "label": conv["label"],
                "category": conv["category"],
                "proposals": scored_proposals,
                "mean_score": mean,
                "proposal_count": len(proposals),
                "pass": True,
                "note": "dry-run",
            }
        else:
            result = judge_conversation(conv, proposals, api_key, judge_model)

        results.append(result)

        if result["proposals"]:
            all_proposals_scored.extend(result["proposals"])

        status = "PASS" if result["pass"] else "FAIL"
        mean_str = f"{result['mean_score']:.2f}" if result["mean_score"] is not None else "—"
        print(f"{status} ({result['proposal_count']} proposals, mean={mean_str})")
        if result.get("note"):
            print(f"    NOTE: {result['note']}")
        for sp in result["proposals"]:
            print(f"    [{sp['score']}] {sp['proposal'][:80]}")

    # ---------------------------------------------------------------------------
    # Aggregate scoring
    # ---------------------------------------------------------------------------

    total_proposals = len(all_proposals_scored)
    if total_proposals > 0:
        global_mean = sum(s["score"] for s in all_proposals_scored) / total_proposals
        score_0_count = sum(1 for s in all_proposals_scored if s["score"] == 0)
        hallucination_rate = score_0_count / total_proposals
    else:
        global_mean = 0.0
        hallucination_rate = 0.0

    passed_conversations = sum(1 for r in results if r["pass"])
    total_conversations = len(results)
    threshold_met = global_mean >= 1.5
    hallucination_ok = hallucination_rate < 0.15

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Total conversations:  {total_conversations}")
    print(f"  Conversations passed: {passed_conversations} / {total_conversations}")
    print(f"  Total proposals:      {total_proposals}")
    print(f"  Global mean score:    {global_mean:.2f} (target ≥ 1.50)")
    print(f"  Score-0 rate:         {hallucination_rate:.1%} (target < 15%)")
    print()
    print(f"  Mean score threshold:     {'PASS ✓' if threshold_met else 'FAIL ✗'}")
    print(f"  Hallucination rate:       {'PASS ✓' if hallucination_ok else 'FAIL ✗'}")
    print()

    overall_pass = threshold_met and hallucination_ok

    if dry_run:
        print("DRY RUN — framework validated. Run without DRY_RUN=1 for real results.")
        verdict = "DRY_RUN_OK"
    elif overall_pass:
        print("VERDICT: PASS — Active Memory proposal quality meets threshold.")
        verdict = "PASS"
    else:
        print("VERDICT: FAIL — See failures above. Consider prompt adjustment.")
        verdict = "FAIL"

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    output_path = results_dir / f"{timestamp}-active-memory-eval.json"

    output = {
        "eval": "active_memory_proposal_quality",
        "ticket": "KIN-328",
        "timestamp": timestamp,
        "dry_run": dry_run,
        "config": {"gen_model": gen_model, "judge_model": judge_model},
        "summary": {
            "total_conversations": total_conversations,
            "conversations_passed": passed_conversations,
            "total_proposals": total_proposals,
            "global_mean_score": round(global_mean, 4),
            "hallucination_rate": round(hallucination_rate, 4),
            "threshold_met": threshold_met,
            "hallucination_ok": hallucination_ok,
            "verdict": verdict,
        },
        "results": results,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {output_path}")

    sys.exit(0 if overall_pass or dry_run else 1)


if __name__ == "__main__":
    run_eval()
