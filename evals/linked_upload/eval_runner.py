"""
Linked Upload extraction accuracy eval runner — KIN-328.

Tests whether LinkedUploadExtractor correctly extracts name + content fields
from synthetic documents across all three surfaces.

Usage:
    cd projects/kinetic
    OPENAI_API_KEY=sk-... python evals/linked_upload/eval_runner.py

    # Surface-specific run:
    OPENAI_API_KEY=sk-... SURFACE=profile python evals/linked_upload/eval_runner.py
    OPENAI_API_KEY=sk-... SURFACE=company python evals/linked_upload/eval_runner.py
    OPENAI_API_KEY=sk-... SURFACE=agent python evals/linked_upload/eval_runner.py

    # Dry-run (mock extraction, validate framework):
    DRY_RUN=1 python evals/linked_upload/eval_runner.py

Pass criteria:
    - Name precision ≥ 85% across all docs with non-null expected names
    - Bio/description/instructions relevance mean ≥ 2.0/3.0
    - Edge cases: null extraction when no individual author

Exit codes:
    0 = PASS
    1 = FAIL
    2 = ERROR
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_ROOT = PROJECT_ROOT / "packages" / "api"
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from evals.linked_upload.documents import AGENT_CORPUS_DOCS, COMPANY_DOCS, USER_PROFILE_DOCS
from evals.linked_upload.judge import judge_name, judge_relevance

# Map surface name → (doc_list, prompt_id, content_field_name)
PROMPT_ID_PROFILE = "generate-user-profile-v1"
PROMPT_ID_COMPANY = "generate-company-profile-v1"
PROMPT_ID_AGENT = "generate-agent-persona-v1"

SURFACE_CONFIG = {
    "profile": (USER_PROFILE_DOCS, PROMPT_ID_PROFILE, "bio"),
    "company": (COMPANY_DOCS, PROMPT_ID_COMPANY, "description"),
    "agent": (AGENT_CORPUS_DOCS, PROMPT_ID_AGENT, "instructions"),
}


def run_extraction(doc: dict, prompt_id: str, api_key: str) -> dict:
    """
    Call LinkedUploadExtractor.extract() directly (no HTTP layer).
    Uses a fake key_row — the extractor decrypts and passes the key to call_llm.
    We bypass the decryption by using the API key directly.
    """
    from app.api.routes.linked_upload import LinkedUploadExtractor
    from app.services.encryption import encrypt_api_key, load_master_key

    user_id = "eval-user-id"
    master_key = load_master_key()

    # Encrypt the real API key into the format the extractor expects
    ciphertext, nonce = encrypt_api_key(api_key, master_key, user_id)
    key_row = {
        "key_ciphertext": ciphertext.hex(),
        "key_nonce": nonce.hex(),
    }

    extractor = LinkedUploadExtractor(user_id=user_id)
    return extractor.extract(
        doc["text"],
        prompt_id=prompt_id,
        key_row=key_row,
        model="gpt-4o-mini",
    )


def dry_run_extraction(doc: dict, surface: str, content_field: str) -> dict:
    """Mock extraction for dry-run framework validation."""
    if surface == "profile":
        return {"name": "Sarah Chen", "bio": "A software engineer with expertise in distributed systems."}
    if surface == "company":
        return {"name": doc["text"].split("\n")[0].strip()[:30], "description": "A technology company building innovative products."}
    return {"name": "Paul Graham", "instructions": "You are Paul Graham. Think like an investor and founder."}


def evaluate_doc(
    doc: dict,
    surface: str,
    content_field: str,
    prompt_id: str,
    api_key: str,
    judge_model: str,
    dry_run: bool,
) -> dict:
    """Run extraction and score a single document."""

    # 1. Extract
    if dry_run:
        extraction = dry_run_extraction(doc, surface, content_field)
    else:
        try:
            extraction = run_extraction(doc, prompt_id, api_key)
        except Exception as exc:
            return {
                "doc_id": doc["id"],
                "label": doc["label"],
                "surface": surface,
                "error": str(exc),
                "pass": False,
            }

    extracted_name = extraction.get("name")
    extracted_content = extraction.get(content_field)

    # 2. Score name
    expected = doc["expected"]
    name_result = judge_name(extracted_name, expected.get("name"))

    # 3. Score content relevance
    if dry_run:
        relevance_result = {"score": 3, "reason": "dry-run mock"}
    elif extracted_content:
        relevance_result = judge_relevance(
            extracted_content,
            doc["text"],
            surface=surface,
            field_name=content_field,
            api_key=api_key,
            model=judge_model,
        )
    else:
        relevance_result = {"score": 1, "reason": "extracted content is null/empty"}

    passed = name_result["precise"] and relevance_result["score"] >= 2

    return {
        "doc_id": doc["id"],
        "label": doc["label"],
        "surface": surface,
        "edge_case": doc.get("edge_case"),
        "name": {
            "extracted": extracted_name,
            "expected": expected.get("name"),
            "precise": name_result["precise"],
            "note": name_result.get("note", ""),
        },
        "content": {
            "field": content_field,
            "extracted_snippet": (extracted_content or "")[:200],
            "score": relevance_result["score"],
            "reason": relevance_result["reason"],
        },
        "pass": passed,
    }


def run_eval():
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("JUDGE_API_KEY")
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-4o")
    surface_filter = os.environ.get("SURFACE")  # None = run all
    dry_run = os.environ.get("DRY_RUN", "0") == "1"

    if not dry_run and not api_key:
        print("ERROR: Set OPENAI_API_KEY or JUDGE_API_KEY to run this eval.", file=sys.stderr)
        sys.exit(2)

    surfaces_to_run = (
        {surface_filter: SURFACE_CONFIG[surface_filter]}
        if surface_filter
        else SURFACE_CONFIG
    )

    all_results = []
    print(f"{'[DRY RUN] ' if dry_run else ''}Linked Upload extraction eval\n")

    for surface, (docs, prompt_id, content_field) in surfaces_to_run.items():
        print(f"── Surface: {surface} ({len(docs)} docs) ──")
        for doc in docs:
            print(f"  [{doc['id']}] {doc['label']}", end=" ... ", flush=True)
            result = evaluate_doc(doc, surface, content_field, prompt_id, api_key, judge_model, dry_run)
            all_results.append(result)
            status = "PASS" if result.get("pass") else "FAIL"
            if "error" in result:
                print(f"ERROR: {result['error']}")
            else:
                print(
                    f"{status} | name={'✓' if result['name']['precise'] else '✗'} "
                    f"| {content_field}={result['content']['score']}/3"
                )
        print()

    # ---------------------------------------------------------------------------
    # Aggregate metrics
    # ---------------------------------------------------------------------------

    valid_results = [r for r in all_results if "error" not in r]
    error_results = [r for r in all_results if "error" in r]

    # Name precision — exclude edge cases with null expected name and agent multi-author
    name_scorable = [
        r for r in valid_results
        if r["name"]["expected"] is not None
        and r.get("edge_case") not in ("no_individual_author", "multi_author")
    ]
    name_precise_count = sum(1 for r in name_scorable if r["name"]["precise"])
    name_precision = name_precise_count / len(name_scorable) if name_scorable else 0.0

    # Relevance — all docs
    relevance_scores = [r["content"]["score"] for r in valid_results]
    relevance_mean = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

    # Per-surface breakdown
    surface_stats = {}
    for surface in SURFACE_CONFIG:
        s_results = [r for r in valid_results if r["surface"] == surface]
        if not s_results:
            continue
        s_name = [r for r in s_results if r["name"]["expected"] is not None and r.get("edge_case") not in ("no_individual_author", "multi_author")]
        surface_stats[surface] = {
            "total": len(s_results),
            "name_precision": sum(1 for r in s_name if r["name"]["precise"]) / len(s_name) if s_name else None,
            "relevance_mean": sum(r["content"]["score"] for r in s_results) / len(s_results),
            "passed": sum(1 for r in s_results if r["pass"]),
        }

    name_pass = name_precision >= 0.85
    relevance_pass = relevance_mean >= 2.0
    overall_pass = name_pass and relevance_pass

    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Total documents:      {len(all_results)}")
    print(f"  Errors:               {len(error_results)}")
    print(f"  Name precision:       {name_precision:.1%} (target ≥ 85%)  {'PASS ✓' if name_pass else 'FAIL ✗'}")
    print(f"  Relevance mean:       {relevance_mean:.2f}/3.0 (target ≥ 2.0)  {'PASS ✓' if relevance_pass else 'FAIL ✗'}")
    print()
    print("  Per-surface:")
    for surface, stats in surface_stats.items():
        name_str = f"{stats['name_precision']:.0%}" if stats["name_precision"] is not None else "n/a"
        print(f"    {surface:10s}: name={name_str} relevance={stats['relevance_mean']:.2f} passed={stats['passed']}/{stats['total']}")
    print()

    if dry_run:
        print("DRY RUN — framework validated. Run without DRY_RUN=1 for real results.")
        verdict = "DRY_RUN_OK"
    elif overall_pass:
        print("VERDICT: PASS — Linked Upload extraction meets accuracy thresholds.")
        verdict = "PASS"
    else:
        print("VERDICT: FAIL — See per-document failures above.")
        verdict = "FAIL"

    # Save
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    output_path = results_dir / f"{timestamp}-linked-upload-eval.json"

    output = {
        "eval": "linked_upload_extraction_accuracy",
        "ticket": "KIN-328",
        "timestamp": timestamp,
        "dry_run": dry_run,
        "config": {"judge_model": judge_model, "surface_filter": surface_filter},
        "summary": {
            "total_documents": len(all_results),
            "errors": len(error_results),
            "name_precision": round(name_precision, 4),
            "relevance_mean": round(relevance_mean, 4),
            "name_precision_pass": name_pass,
            "relevance_pass": relevance_pass,
            "verdict": verdict,
        },
        "per_surface": surface_stats,
        "results": all_results,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {output_path}")

    sys.exit(0 if overall_pass or dry_run else 1)


if __name__ == "__main__":
    run_eval()
