"""
Nate Eval A — Founder/CEO persona eval runner.

Measures how well the Nate B. Jones agent performs for Persona A (Founder/CEO)
as defined in ``jtbd-nate-agent.md``. Runs 4 binary Pass/Fail judges against
each generation response.

Four failure modes evaluated (one judge each):
    1. specificity   — Does Nate give a specific verdict, or a generic menu?
    2. context_use   — Does Nate use injected company context?
    3. voice         — Does Nate sound like Nate (direct, no hedging)?
    4. ai_expertise  — Does the response reflect real AI transformation expertise?

Pass bar: all 4 judges must average >= 80% Pass rate across all test cases.

Usage:
    cd projects/kinetic/packages/api
    python -m evals.nate_eval_a.eval [--dry-run] [--output-dir <path>]

Environment variables:
    JUDGE_MODEL            — model for judge calls (default: gpt-4o)
    JUDGE_API_KEY          — API key for the judge model provider (required)
    GEN_MODEL              — model used by Kinetic for generation (default: gpt-4o)
    GEN_API_KEY            — user BYOK API key registered in Kinetic prod (required)
    KINETIC_API_URL        — Kinetic prod base URL
                             (default: https://kinetic-production-b568.up.railway.app)
    KINETIC_USER_TOKEN     — Supabase session JWT for the Kinetic prod user (required)
    KINETIC_CONVERSATION_ID— active Kinetic conversation UUID (required)
    KINETIC_AGENT_ID       — Nate agent definition UUID (optional — activates agent)
    DRY_RUN                — set to "1" to run with mock outputs, no API calls

Notes on generation approach:
    Kinetic's generation endpoint is a stateful SSE stream that requires an
    authenticated Kinetic user, an active conversation scoped to a project with
    the Nate agent, and a message POST to /api/v1/conversations/{id}/generate.

    For eval purposes the runner sends the test prompt with the context fixture
    prepended as a clearly delimited block. This simulates what Kinetic's L1-L5
    context stack does for a real user session with persistent memory configured.

Exit codes:
    0 — all 4 judges passed (>= 80% pass rate across test cases)
    1 — one or more judges failed (< 80% pass rate)
    2 — runner error (missing env vars, API failures, etc.)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Resolve dataset + judges (same package)
# ---------------------------------------------------------------------------

# Add packages/api root to path so package imports work when invoked as a
# module from packages/api/ (consistent with existing eval runners).
_HERE = os.path.dirname(os.path.abspath(__file__))
_EVALS_ROOT = os.path.dirname(_HERE)
_API_ROOT = os.path.dirname(_EVALS_ROOT)
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

from evals.nate_eval_a.data import (  # noqa: E402
    TEST_CASES,
    NEGATIVE_CONTROLS,
    DRY_RUN_MOCK_RESPONSE,
)
from evals.nate_eval_a.judges import JUDGES, JUDGE_NAMES  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KINETIC_API_URL = os.environ.get(
    "KINETIC_API_URL", "https://kinetic-production-b568.up.railway.app"
).rstrip("/")

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-4o")
GEN_MODEL = os.environ.get("GEN_MODEL", "gpt-4o")
# llm_models.id UUID for the generation model — defaults to Claude Sonnet 4.6
KINETIC_MODEL_ID = os.environ.get(
    "KINETIC_MODEL_ID", "aa1b0d8e-8c54-4d91-bb27-2ed7a44d2ebd"
)
# Brandon's "AI Consulting" company in prod — used to scope fresh conversations
KINETIC_COMPANY_ID = os.environ.get(
    "KINETIC_COMPANY_ID", "51d96aaf-2a73-42bd-b3e4-397084f543d7"
)
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

PASS_THRESHOLD = 0.80  # Each judge must achieve >= 80% pass rate to pass the suite

# Judge verdict regex — extracts the word immediately inside <verdict>...</verdict>
_VERDICT_RE = re.compile(r"<verdict>\s*(PASS|FAIL)\s*</verdict>", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Generation — call Kinetic API via SSE
# ---------------------------------------------------------------------------


def _build_generation_prompt(prompt: str, context: str) -> str:
    """Combine the context fixture with the test prompt.

    The context is prepended with a clear delimiter so it reads as injected
    background information rather than the user's message. This simulates what
    Kinetic's L1-L5 context stack does for a real session.
    """
    return (
        f"[KINETIC CONTEXT — Your persistent memory for this user]\n"
        f"{context}\n"
        f"[END KINETIC CONTEXT]\n\n"
        f"{prompt}"
    )


def _parse_sse_stream(raw: str) -> str:
    """Parse Server-Sent Events stream text and concatenate delta content.

    SSE format from Kinetic's generation endpoint:
        data: {"type": "delta", "content": "chunk text"}
        data: {"type": "done", "message_id": "uuid", ...}
        data: {"type": "error", "message": "..."}
    """
    lines = raw.splitlines()
    parts: list[str] = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "delta":
            parts.append(event.get("content", ""))
        elif event.get("type") == "error":
            raise RuntimeError(
                f"Kinetic generation error: {event.get('message', 'unknown')}"
            )
    return "".join(parts)


def create_conversation(
    kinetic_user_token: str,
    company_id: str,
    agent_id: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """Create a fresh Kinetic conversation and return its UUID.

    Each test case gets its own conversation so prior-case context never bleeds
    into the next response. Without this, the agent eventually sees a long
    accumulated history and stops responding to the current prompt on its merits.

    Raises:
        RuntimeError: on HTTP error or empty response.
    """
    import http.client
    from urllib.parse import urlparse

    body: dict = {"company_id": company_id}
    if agent_id:
        body["active_agent_id"] = agent_id
    if title:
        body["title"] = title

    body_bytes = json.dumps(body).encode("utf-8")
    parsed = urlparse(KINETIC_API_URL)
    host = parsed.netloc

    if parsed.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(host, timeout=30)
    else:
        conn = http.client.HTTPConnection(host, timeout=30)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {kinetic_user_token}",
        "Content-Length": str(len(body_bytes)),
    }

    conn.request("POST", "/api/v1/conversations", body=body_bytes, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()

    if resp.status not in (200, 201):
        raise RuntimeError(
            f"create_conversation: API returned {resp.status}: {raw[:300]}"
        )

    data = json.loads(raw)
    conv_id = data.get("id")
    if not conv_id:
        raise RuntimeError(f"create_conversation: no id in response: {raw[:200]}")
    return conv_id


def generate_response(
    prompt: str,
    context: str,
    kinetic_user_token: str,
    conversation_id: str,
    agent_id: Optional[str] = None,
) -> str:
    """Call Kinetic's generation endpoint and return the full response text.

    Uses stdlib ``http.client`` only — no new dependencies required.

    Args:
        prompt: The test prompt to send to Nate.
        context: The context fixture to inject as a preamble.
        kinetic_user_token: Supabase session JWT for the Kinetic prod user.
        conversation_id: An active Kinetic conversation UUID scoped to a project
            with the Nate agent active.
        agent_id: Optional Nate agent definition UUID. If provided, activates
            the Nate agent for this conversation turn.

    Returns:
        Full response text from the Nate agent (concatenated SSE deltas).

    Raises:
        RuntimeError: on HTTP error, SSE error, or empty response.
    """
    import http.client
    from urllib.parse import urlparse

    full_prompt = _build_generation_prompt(prompt, context)
    body: dict = {"message": full_prompt, "model_id": KINETIC_MODEL_ID}
    if agent_id:
        body["agent_id"] = agent_id

    body_bytes = json.dumps(body).encode("utf-8")
    parsed = urlparse(KINETIC_API_URL)
    host = parsed.netloc
    path = f"/api/v1/conversations/{conversation_id}/generate"

    if parsed.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(host, timeout=120)
    else:
        conn = http.client.HTTPConnection(host, timeout=120)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {kinetic_user_token}",
        "Accept": "text/event-stream",
        "Content-Length": str(len(body_bytes)),
    }

    conn.request("POST", path, body=body_bytes, headers=headers)
    resp = conn.getresponse()

    if resp.status != 200:
        body_text = resp.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Kinetic API returned {resp.status}: {body_text[:300]}"
        )

    # Read the full SSE stream to completion
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()

    text = _parse_sse_stream(raw)
    if not text.strip():
        raise RuntimeError(
            "Kinetic returned an empty response — check conversation_id, "
            "agent activation, and Nate system prompt configuration."
        )
    return text


# ---------------------------------------------------------------------------
# Judge execution — call judge LLM via OpenAI-compatible API
# ---------------------------------------------------------------------------


def _build_judge_input(case: dict, response: str) -> str:
    """Build the user message for the judge LLM.

    Includes the injected context, the user's prompt, and Nate's response so
    the judge has full information to evaluate context_use (judge 2) as well
    as the other dimensions.
    """
    return (
        f"## Injected Context (what Kinetic provided to the agent)\n\n"
        f"{case['context']}\n\n"
        f"## User Prompt\n\n"
        f"{case['prompt']}\n\n"
        f"## Nate's Response\n\n"
        f"{response}"
    )


def run_judge(
    judge_name: str,
    judge_prompt: str,
    judge_input: str,
    judge_api_key: str,
) -> dict:
    """Call the judge LLM and extract a binary PASS/FAIL verdict.

    Uses OpenAI-compatible chat completions API via stdlib ``http.client``.

    Args:
        judge_name: One of the JUDGE_NAMES.
        judge_prompt: The judge's system prompt (from judges.py).
        judge_input: The formatted case + response text (user message).
        judge_api_key: API key for the judge model provider.

    Returns:
        {
            "judge": str,
            "verdict": "PASS" | "FAIL" | "ERROR",
            "critique": str,   # text between <critique>...</critique>
            "raw_output": str, # full judge model output
            "error": str | None,
        }
    """
    import http.client

    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": judge_prompt},
            {"role": "user", "content": judge_input},
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {judge_api_key}",
        "Content-Length": str(len(payload_bytes)),
    }

    # Retry on 429 (rate limit) with exponential backoff
    raw_bytes = b""
    status = 0
    for attempt in range(4):
        conn = http.client.HTTPSConnection("api.openai.com", timeout=60)
        conn.request("POST", "/v1/chat/completions", body=payload_bytes, headers=headers)
        resp = conn.getresponse()
        raw_bytes = resp.read()
        status = resp.status
        conn.close()
        if status != 429:
            break
        # 429: back off and retry (2s, 4s, 8s)
        backoff = 2 ** (attempt + 1)
        print(
            f" [429 — backing off {backoff}s, attempt {attempt + 1}/4]",
            file=sys.stderr,
            end="",
        )
        time.sleep(backoff)

    if status != 200:
        err_text = raw_bytes.decode("utf-8", errors="replace")[:300]
        return {
            "judge": judge_name,
            "verdict": "ERROR",
            "critique": "",
            "raw_output": err_text,
            "error": f"Judge API returned {status}: {err_text}",
        }

    data = json.loads(raw_bytes)
    content: str = data["choices"][0]["message"]["content"]

    # Extract verdict
    match = _VERDICT_RE.search(content)
    verdict = match.group(1).upper() if match else "ERROR"
    error: Optional[str] = None if match else "No <verdict> tag found in judge output"

    # Extract critique
    critique_match = re.search(
        r"<critique>(.*?)</critique>", content, re.IGNORECASE | re.DOTALL
    )
    critique = critique_match.group(1).strip() if critique_match else ""

    return {
        "judge": judge_name,
        "verdict": verdict,
        "critique": critique,
        "raw_output": content,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


def _dry_run_generate() -> str:
    """Return the mock generation response for dry-run mode."""
    return DRY_RUN_MOCK_RESPONSE


def _dry_run_judge(judge_name: str, case_id: str) -> dict:
    """Return a deterministic mock judge result for dry-run mode.

    Alternates PASS/FAIL based on (judge index + case number) % 3 so that the
    dry-run exercises both verdict paths and tests the aggregation logic.
    """
    judge_index = JUDGE_NAMES.index(judge_name)
    # Extract leading digits from the case ID (e.g., "A05" -> 5, "NC01-foo" -> 0)
    digits = "".join(ch for ch in case_id if ch.isdigit())
    case_num = int(digits) if digits else 0
    verdict = "PASS" if (judge_index + case_num) % 3 != 0 else "FAIL"
    return {
        "judge": judge_name,
        "verdict": verdict,
        "critique": f"[DRY RUN] Mock critique for {judge_name} on case {case_id}.",
        "raw_output": (
            f"<critique>[DRY RUN] Mock critique.</critique>\n<verdict>{verdict}</verdict>"
        ),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------


def evaluate_case(
    case: dict,
    kinetic_user_token: str,
    conversation_id: str,
    judge_api_key: str,
    agent_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Generate a response for one test case and run all 4 judges.

    Returns a dict with keys:
        id, prompt, trigger, axis_a, axis_b, axis_c,
        response, response_error,
        judges: {judge_name: {verdict, critique, error}},
        pass_count, judge_count
    """
    case_id = case["id"]
    is_negative_control = "bad_response_override" in case
    label = "[NEG-CTRL]" if is_negative_control else ""
    print(f"  [{case_id}]{label} {case['prompt'][:55]}...", file=sys.stderr, end="")

    # Step 1: Generate (or use hardcoded bad response for negative controls)
    response_error: Optional[str] = None
    case_conversation_id: Optional[str] = None
    if is_negative_control:
        response = case["bad_response_override"]
        print(" [HARDCODED]", file=sys.stderr, end="")
    elif dry_run:
        response = _dry_run_generate()
        print(" [DRY RUN]", file=sys.stderr, end="")
    else:
        try:
            # Fresh conversation per case — prevents prior-case history from
            # polluting the response (e.g., agent refusing to repeat itself).
            case_conversation_id = create_conversation(
                kinetic_user_token=kinetic_user_token,
                company_id=KINETIC_COMPANY_ID,
                agent_id=agent_id,
                title=f"Eval A — {case_id}",
            )
            response = generate_response(
                prompt=case["prompt"],
                context=case["context"],
                kinetic_user_token=kinetic_user_token,
                conversation_id=case_conversation_id,
                agent_id=agent_id,
            )
        except Exception as exc:
            response = ""
            response_error = str(exc)
            print(f" GENERATION_ERROR: {exc}", file=sys.stderr)

    # Step 2: Run all 4 judges
    judge_results: dict[str, dict] = {}
    pass_count = 0

    if response_error:
        # Cannot judge an empty response — mark all as ERROR
        for judge_name in JUDGE_NAMES:
            judge_results[judge_name] = {
                "judge": judge_name,
                "verdict": "ERROR",
                "critique": "",
                "raw_output": "",
                "error": f"Skipped — generation failed: {response_error}",
            }
    else:
        judge_input = _build_judge_input(case, response)
        for judge_name, judge_prompt in JUDGES.items():
            if dry_run:
                result = _dry_run_judge(judge_name, case_id)
            else:
                result = run_judge(judge_name, judge_prompt, judge_input, judge_api_key)
            judge_results[judge_name] = result
            if result["verdict"] == "PASS":
                pass_count += 1

    valid_verdicts = [
        r for r in judge_results.values() if r["verdict"] in ("PASS", "FAIL")
    ]
    judge_count = len(valid_verdicts)

    summary = " ".join(
        f"{name[0].upper()}="
        f"{'P' if judge_results[name]['verdict'] == 'PASS' else 'F' if judge_results[name]['verdict'] == 'FAIL' else 'E'}"
        for name in JUDGE_NAMES
    )
    print(f" [{summary}]", file=sys.stderr)

    return {
        "id": case_id,
        "prompt": case["prompt"],
        "trigger": case.get("trigger"),
        "axis_a": case.get("axis_a"),
        "axis_b": case.get("axis_b"),
        "axis_c": case.get("axis_c"),
        "is_negative_control": is_negative_control,
        "expected_fails": case.get("expected_fails", []),
        "expected_passes": case.get("expected_passes", []),
        "case_conversation_id": case_conversation_id,
        "response": response,
        "response_error": response_error,
        "judges": judge_results,
        "pass_count": pass_count,
        "judge_count": judge_count,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(results: list[dict]) -> dict:
    """Compute per-judge pass rates, suite verdict, and judge calibration.

    Negative controls are excluded from the main pass-rate metrics and tracked
    separately in ``judge_calibration``. A judge is calibrated if it returns
    the expected verdict on every negative control.
    """
    # Split real cases from negative controls
    real_cases = [r for r in results if not r.get("is_negative_control")]
    neg_controls = [r for r in results if r.get("is_negative_control")]

    total_cases = len(real_cases)
    generation_errors = sum(1 for r in real_cases if r.get("response_error"))

    judge_pass_counts: dict[str, int] = {j: 0 for j in JUDGE_NAMES}
    judge_valid_counts: dict[str, int] = {j: 0 for j in JUDGE_NAMES}
    judge_error_counts: dict[str, int] = {j: 0 for j in JUDGE_NAMES}

    for result in real_cases:
        for judge_name, jresult in result.get("judges", {}).items():
            verdict = jresult.get("verdict", "ERROR")
            if verdict == "PASS":
                judge_pass_counts[judge_name] += 1
                judge_valid_counts[judge_name] += 1
            elif verdict == "FAIL":
                judge_valid_counts[judge_name] += 1
            else:
                judge_error_counts[judge_name] += 1

    judge_pass_rates: dict[str, float] = {}
    for judge_name in JUDGE_NAMES:
        valid = judge_valid_counts[judge_name]
        judge_pass_rates[judge_name] = (
            round(judge_pass_counts[judge_name] / valid, 4) if valid > 0 else 0.0
        )

    launch_bars = {
        judge_name: {
            "rate": judge_pass_rates[judge_name],
            "target": PASS_THRESHOLD,
            "met": judge_pass_rates[judge_name] >= PASS_THRESHOLD,
        }
        for judge_name in JUDGE_NAMES
    }

    # Judge calibration — verify judges return expected verdicts on negative controls
    calibration: dict[str, dict] = {
        j: {"expected_fail_caught": 0, "expected_fail_missed": 0,
            "expected_pass_caught": 0, "expected_pass_missed": 0,
            "errors": 0, "violations": []}
        for j in JUDGE_NAMES
    }
    for nc in neg_controls:
        expected_fails = set(nc.get("expected_fails", []))
        expected_passes = set(nc.get("expected_passes", []))
        for judge_name, jresult in nc.get("judges", {}).items():
            verdict = jresult.get("verdict", "ERROR")
            if verdict == "ERROR":
                calibration[judge_name]["errors"] += 1
                continue
            if judge_name in expected_fails:
                if verdict == "FAIL":
                    calibration[judge_name]["expected_fail_caught"] += 1
                else:
                    calibration[judge_name]["expected_fail_missed"] += 1
                    calibration[judge_name]["violations"].append(
                        f"{nc['id']}: expected FAIL, got PASS"
                    )
            elif judge_name in expected_passes:
                if verdict == "PASS":
                    calibration[judge_name]["expected_pass_caught"] += 1
                else:
                    calibration[judge_name]["expected_pass_missed"] += 1
                    calibration[judge_name]["violations"].append(
                        f"{nc['id']}: expected PASS, got FAIL"
                    )

    # A judge is calibrated if it caught every expected outcome (no violations)
    judges_calibrated = {
        j: len(calibration[j]["violations"]) == 0 and calibration[j]["errors"] == 0
        for j in JUDGE_NAMES
    }
    all_judges_calibrated = all(judges_calibrated.values())

    # Suite pass requires both: launch bars met AND judges calibrated
    suite_pass = all(bar["met"] for bar in launch_bars.values()) and all_judges_calibrated

    total_judge_calls = sum(len(r.get("judges", {})) for r in results)
    total_judge_errors = sum(judge_error_counts.values())

    # Break down pass rates by trigger situation (real cases only)
    triggers: dict[str, dict] = {}
    for result in real_cases:
        trigger = result.get("trigger", "unknown")
        if trigger not in triggers:
            triggers[trigger] = {"total": 0, "pass_counts": []}
        triggers[trigger]["total"] += 1
        valid = [
            r for r in result.get("judges", {}).values()
            if r.get("verdict") in ("PASS", "FAIL")
        ]
        if valid:
            rate = sum(1 for r in valid if r["verdict"] == "PASS") / len(valid)
            triggers[trigger]["pass_counts"].append(rate)

    by_trigger = {
        trigger: {
            "total": data["total"],
            "avg_pass_rate": round(
                sum(data["pass_counts"]) / len(data["pass_counts"]), 4
            ) if data["pass_counts"] else 0.0,
        }
        for trigger, data in triggers.items()
    }

    return {
        "judge_pass_rates": judge_pass_rates,
        "judge_error_counts": judge_error_counts,
        "launch_bars": launch_bars,
        "judge_calibration": calibration,
        "judges_calibrated": judges_calibrated,
        "all_judges_calibrated": all_judges_calibrated,
        "suite_pass": suite_pass,
        "counts": {
            "total_cases": total_cases,
            "negative_controls": len(neg_controls),
            "generation_errors": generation_errors,
            "total_judge_calls": total_judge_calls,
            "judge_errors": total_judge_errors,
        },
        "by_trigger": by_trigger,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(metrics: dict, results: list[dict]) -> None:
    """Print a human-readable eval report to stdout."""
    print("\n" + "=" * 65)
    print("NATE EVAL A — FOUNDER/CEO PERSONA RESULTS")
    print("=" * 65)

    c = metrics["counts"]
    print(f"\nDataset: {c['total_cases']} cases")
    if c["generation_errors"]:
        print(f"  Generation errors: {c['generation_errors']} (cases skipped)")
    if c["judge_errors"]:
        print(f"  Judge errors:      {c['judge_errors']} (calls not scored)")

    print("\n--- Per-Judge Pass Rates vs Launch Bar (>= 80%) ---")
    for judge_name, bar in metrics["launch_bars"].items():
        symbol = "PASS" if bar["met"] else "FAIL"
        err_count = metrics["judge_error_counts"].get(judge_name, 0)
        err_note = f"  [{err_count} errors]" if err_count else ""
        print(
            f"  [{symbol}] {judge_name:18s}  {bar['rate']:6.1%}  "
            f"(target >= {bar['target']:.0%}){err_note}"
        )

    # Judge calibration block
    print("\n--- Judge Calibration (Negative Controls) ---")
    nc_count = metrics["counts"].get("negative_controls", 0)
    if nc_count == 0:
        print("  (no negative controls — judges UNCALIBRATED, suite unreliable)")
    else:
        print(f"  {nc_count} negative control case(s) checked")
        for judge_name in JUDGE_NAMES:
            cal = metrics["judge_calibration"][judge_name]
            calibrated = metrics["judges_calibrated"][judge_name]
            symbol = "PASS" if calibrated else "FAIL"
            caught = cal["expected_fail_caught"] + cal["expected_pass_caught"]
            missed = cal["expected_fail_missed"] + cal["expected_pass_missed"]
            errs = cal["errors"]
            total = caught + missed
            print(
                f"  [{symbol}] {judge_name:18s}  {caught}/{total} expected verdicts caught"
                f"{f' [{errs} errors]' if errs else ''}"
            )
            for v in cal["violations"]:
                print(f"        VIOLATION: {v}")

    suite_result = "PASS" if metrics["suite_pass"] else "FAIL"
    print(f"\n  Suite result: {suite_result}")
    print(
        "  (Suite PASS requires: all 4 judges >= 80% pass rate on real cases "
        "AND all 4 judges calibrated on negative controls)"
    )

    print("\n--- Pass Rate by Trigger Situation ---")
    for trigger, data in sorted(metrics["by_trigger"].items()):
        print(
            f"  {trigger:15s}  {data['total']} cases  "
            f"avg_pass_rate={data['avg_pass_rate']:.1%}"
        )

    # Show cases with at least one FAIL
    failures = [
        r for r in results
        if any(
            j.get("verdict") == "FAIL"
            for j in r.get("judges", {}).values()
        )
    ]
    if failures:
        print(f"\n--- Cases with at Least One Judge FAIL ({len(failures)}) ---")
        for r in failures[:10]:
            failed_judges = [
                name for name, j in r.get("judges", {}).items()
                if j.get("verdict") == "FAIL"
            ]
            print(f'  [{r["id"]}] [{r.get("trigger", "?")}] "{r["prompt"][:55]}..."')
            print(f"        Failed judges: {', '.join(failed_judges)}")
            for name in failed_judges:
                critique = r["judges"][name].get("critique", "")
                if critique:
                    print(f"        [{name}] {critique[:150]}")

    print("\n" + "=" * 65)


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------


def save_results(
    results: list[dict],
    metrics: dict,
    output_dir: str,
    dry_run: bool,
) -> str:
    """Save JSON results to output_dir. Returns the results file path."""
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "results.json")
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "judge_model": JUDGE_MODEL,
        "gen_model": GEN_MODEL,
        "kinetic_api_url": KINETIC_API_URL,
        "pass_threshold": PASS_THRESHOLD,
        "metrics": metrics,
        "per_case_results": results,
    }
    with open(results_path, "w") as f:
        json.dump(payload, f, indent=2)
    return results_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point. Returns exit code: 0=PASS, 1=FAIL, 2=ERROR."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Nate Eval A — Founder/CEO persona eval runner"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=DRY_RUN,
        help="Run with mock outputs — no API calls (also set DRY_RUN=1)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Output directory for results JSON "
            "(default: timestamped under evals/nate_eval_a/results/)"
        ),
    )
    parser.add_argument(
        "--conversation-id",
        default=os.environ.get("KINETIC_CONVERSATION_ID"),
        help="Kinetic conversation UUID (or set KINETIC_CONVERSATION_ID env var)",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("KINETIC_AGENT_ID"),
        help="Nate agent definition UUID (or set KINETIC_AGENT_ID env var)",
    )
    args = parser.parse_args()

    dry_run: bool = args.dry_run

    if dry_run:
        print(
            "[DRY RUN] Using mock generation outputs. No API calls will be made.",
            file=sys.stderr,
        )
        judge_api_key = "DRY_RUN"
        kinetic_user_token = "DRY_RUN"
    else:
        # Validate required env vars
        missing: list[str] = []
        judge_api_key = os.environ.get("JUDGE_API_KEY", "")
        kinetic_user_token = os.environ.get("KINETIC_USER_TOKEN", "")

        if not judge_api_key:
            missing.append("JUDGE_API_KEY")
        if not kinetic_user_token:
            missing.append("KINETIC_USER_TOKEN")
        # KINETIC_CONVERSATION_ID no longer required — runner creates a fresh
        # conversation per case to avoid history pollution. Kept as fallback.

        if missing:
            print(
                "Error: Missing required env vars / args:\n"
                + "\n".join(f"  - {m}" for m in missing),
                file=sys.stderr,
            )
            print(
                "\nHint: Run with --dry-run to test without API calls.",
                file=sys.stderr,
            )
            return 2

    all_cases = TEST_CASES + NEGATIVE_CONTROLS
    print(
        f"Running Nate Eval A — {len(TEST_CASES)} real cases + "
        f"{len(NEGATIVE_CONTROLS)} negative controls, "
        f"{'DRY RUN' if dry_run else 'LIVE'}",
        file=sys.stderr,
    )
    print(f"  Judge model:   {JUDGE_MODEL}", file=sys.stderr)
    print(f"  Gen model:     {GEN_MODEL}", file=sys.stderr)
    print(f"  Kinetic URL:   {KINETIC_API_URL}", file=sys.stderr)

    # Run all cases
    results: list[dict] = []
    try:
        for case in all_cases:
            result = evaluate_case(
                case=case,
                kinetic_user_token=kinetic_user_token,
                conversation_id=args.conversation_id or "DRY_RUN_CONV_ID",
                judge_api_key=judge_api_key,
                agent_id=args.agent_id,
                dry_run=dry_run,
            )
            results.append(result)
            # Brief pause between cases to avoid rate-limit bursts on live runs
            if not dry_run:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nInterrupted. Saving partial results...", file=sys.stderr)

    if not results:
        print("Error: No results collected.", file=sys.stderr)
        return 2

    # Compute metrics and print report
    metrics = compute_metrics(results)
    print_report(metrics, results)

    # Save results
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or os.path.join(_HERE, "results", ts)
    results_path = save_results(results, metrics, output_dir, dry_run)
    print(f"\nResults saved to {results_path}", file=sys.stderr)

    # Exit codes: 0=PASS, 1=FAIL (suite), 2=ERROR
    return 0 if metrics["suite_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
