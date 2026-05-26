"""One-shot Nate verification — sends a single prompt to prod Nate and prints
the full response. Used to confirm prod prompt updates take effect.

Reuses helpers from the Nate Eval B runner so behavior matches eval traces.

Usage:
    KINETIC_USER_TOKEN=<jwt> python tools/test_nate_one_shot.py <case_id>

Env vars:
    KINETIC_USER_TOKEN     — required, Supabase JWT for Kinetic prod user.
    KINETIC_AGENT_ID       — optional, defaults to Nate prod UUID.
    KINETIC_COMPANY_ID     — optional, defaults to Brandon's AI Consulting company.
    KINETIC_API_URL        — optional, defaults to prod.

Exit codes: 0 ok, 2 missing env, 3 API error.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the evals package importable (tools/ is a sibling of evals/)
API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))

from evals.nate_eval_b.data import TEST_CASES  # noqa: E402
from evals.nate_eval_b.eval import (  # noqa: E402
    KINETIC_API_URL,
    KINETIC_COMPANY_ID,
    create_conversation,
    generate_response,
)

NATE_AGENT_UUID = "9b54b4c3-eec0-44dd-add6-feb368f400e8"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: test_nate_one_shot.py <case_id> (e.g. B04)", file=sys.stderr)
        return 2

    case_id = sys.argv[1]
    case = next((c for c in TEST_CASES if c["id"] == case_id), None)
    if case is None:
        print(f"unknown case id: {case_id}", file=sys.stderr)
        return 2

    token = os.environ.get("KINETIC_USER_TOKEN", "")
    if not token:
        print("missing KINETIC_USER_TOKEN env var", file=sys.stderr)
        return 2

    agent_id = os.environ.get("KINETIC_AGENT_ID") or NATE_AGENT_UUID
    company_id = os.environ.get("KINETIC_COMPANY_ID") or KINETIC_COMPANY_ID

    print(f"[info] API URL:     {KINETIC_API_URL}", file=sys.stderr)
    print(f"[info] Agent ID:    {agent_id}", file=sys.stderr)
    print(f"[info] Company ID:  {company_id}", file=sys.stderr)
    print(f"[info] Case:        {case_id}", file=sys.stderr)
    print(file=sys.stderr)

    try:
        conv_id = create_conversation(
            kinetic_user_token=token,
            company_id=company_id,
            agent_id=agent_id,
            title=f"one_shot_{case_id}_verdict_check",
        )
        print(f"[info] Conversation: {conv_id}", file=sys.stderr)

        response = generate_response(
            prompt=case["prompt"],
            context=case["context"],
            kinetic_user_token=token,
            conversation_id=conv_id,
            agent_id=agent_id,
        )
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3

    print("=" * 70)
    print(f"PROMPT ({case_id}):")
    print("=" * 70)
    print(case["prompt"])
    print()
    print("=" * 70)
    print("RESPONSE:")
    print("=" * 70)
    print(response)
    print()
    print("=" * 70)
    print(f"length: {len(response)} chars; last 80 chars: {response[-80:]!r}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
