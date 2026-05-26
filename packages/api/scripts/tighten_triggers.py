"""
Rewrite framework trigger phrases for pilot 20 frameworks (KIN-443).

Selects 20 frameworks from the highest-usage categories, uses GPT-4o-mini
to generate short, verb-led, user-vocabulary trigger phrases, and optionally
applies updates to the database.

Usage:
    cd packages/api

    # Preview mode (default) — generates new triggers, writes JSON for review:
    python -m scripts.tighten_triggers \
        --agent-slug nate \
        --output scripts/trigger_rewrite_preview.json

    # Apply mode — updates when_to_apply in the database:
    python -m scripts.tighten_triggers \
        --agent-slug nate \
        --apply

    # After applying, run the admin backfill to re-embed (use agent UUID from output):
    curl -X POST "https://kinetic-production-b568.up.railway.app/api/v1/admin/backfill-trigger-embeddings?agent_definition_id=<uuid>" \
        -H "Authorization: Bearer <token>"

Environment variables:
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY (always — for re-embedding);
    OPENAI_API_KEY (only for the gpt-4o-mini trigger-rewrite step — required
    by this script because rewriting is its whole purpose).
"""

import argparse
import json
import os
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# LLM prompt for trigger rewriting
# ---------------------------------------------------------------------------

REWRITE_PROMPT = """You are rewriting trigger phrases for a knowledge framework retrieval system.

Current trigger phrases are written in the framework author's vocabulary. Rewrite them in the user's vocabulary — how a real person would phrase their question or problem.

Framework: {name}
Description: {description}
Current triggers: {current_triggers}

Rewrite rules:
- 5–10 words per trigger phrase
- Verb-led: "diagnose...", "evaluate...", "overcome...", "structure...", "plan..."
- Use the user's vocabulary, not the framework author's jargon
- Each trigger should capture a DISTINCT use case — no redundant paraphrases
- Write 4 trigger phrases (minimum 3, maximum 5)

Respond ONLY with this JSON (no markdown, no explanation):
{{"triggers": ["trigger1", "trigger2", "trigger3", "trigger4"]}}"""


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
        # Show what agents exist to help debug
        all_agents = (
            supabase.table("agent_definitions")
            .select("id, name, slug")
            .execute()
        )
        available = all_agents.data or []
        print(f"Error: No agent found with slug '{slug}'", file=sys.stderr)
        if available:
            print(f"Available agents in this database:", file=sys.stderr)
            for a in available:
                print(f"  - {a.get('name', '?')} (slug: '{a.get('slug', '')}', id: {a['id']})", file=sys.stderr)
        else:
            print(f"No agents exist in this database. Are you pointing at the right Supabase instance?", file=sys.stderr)
        sys.exit(1)
    agent = agents[0]
    print(f"Resolved agent '{slug}' → {agent['name']} ({agent['id']})", file=sys.stderr)
    return agent["id"]


# ---------------------------------------------------------------------------
# Framework fetching + category analysis
# ---------------------------------------------------------------------------

def fetch_frameworks_by_category(supabase, agent_id: str) -> dict:
    """Fetch all frameworks for an agent, grouped by category."""
    result = (
        supabase.table("frameworks")
        .select("id, framework_id, name, description, category, when_to_apply")
        .eq("agent_definition_id", agent_id)
        .execute()
    )
    frameworks = result.data or []

    by_category: dict[str, list[dict]] = {}
    for fw in frameworks:
        cat = fw.get("category") or "uncategorized"
        by_category.setdefault(cat, []).append(fw)

    return by_category


def select_pilot_frameworks(
    by_category: dict[str, list[dict]], count: int = 20
) -> list[dict]:
    """Select frameworks from the largest categories, round-robin."""
    # Sort categories by size (descending)
    sorted_cats = sorted(by_category.keys(), key=lambda c: len(by_category[c]), reverse=True)

    print(f"\nCategory distribution:", file=sys.stderr)
    for cat in sorted_cats:
        print(f"  {cat}: {len(by_category[cat])} frameworks", file=sys.stderr)

    # Round-robin from largest categories until we hit count
    selected: list[dict] = []
    selected_ids: set[str] = set()
    cat_indices = {cat: 0 for cat in sorted_cats}

    while len(selected) < count:
        added_this_round = False
        for cat in sorted_cats:
            if len(selected) >= count:
                break
            idx = cat_indices[cat]
            fws = by_category[cat]
            if idx < len(fws):
                fw = fws[idx]
                if fw["id"] not in selected_ids:
                    selected.append(fw)
                    selected_ids.add(fw["id"])
                    added_this_round = True
                cat_indices[cat] = idx + 1
        if not added_this_round:
            break  # Exhausted all categories

    return selected


# ---------------------------------------------------------------------------
# LLM trigger rewriting
# ---------------------------------------------------------------------------

def rewrite_triggers(
    frameworks: list[dict], openai_key: str
) -> list[dict]:
    """Use GPT-4o-mini to generate new trigger phrases for each framework."""
    import openai

    client = openai.OpenAI(api_key=openai_key)
    results: list[dict] = []
    fail_count = 0

    for i, fw in enumerate(frameworks, 1):
        current = fw.get("when_to_apply") or []
        current_text = ", ".join(current) if isinstance(current, list) else str(current)

        prompt = REWRITE_PROMPT.format(
            name=fw["name"],
            description=fw.get("description") or "(no description)",
            current_triggers=current_text,
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)

            new_triggers = data.get("triggers", [])

            # Validate
            if not new_triggers or len(new_triggers) < 3:
                print(
                    f"  [{i}/{len(frameworks)}] {fw['name']}: "
                    f"WARNING — only {len(new_triggers)} triggers generated, retrying...",
                    file=sys.stderr,
                )
                fail_count += 1
                results.append({
                    "framework_db_id": fw["id"],
                    "framework_id": fw["framework_id"],
                    "name": fw["name"],
                    "category": fw.get("category"),
                    "old_triggers": current,
                    "new_triggers": current,  # Keep old on failure
                    "status": "failed",
                })
                continue

            results.append({
                "framework_db_id": fw["id"],
                "framework_id": fw["framework_id"],
                "name": fw["name"],
                "category": fw.get("category"),
                "old_triggers": current,
                "new_triggers": new_triggers,
                "status": "rewritten",
            })

            print(
                f"  [{i}/{len(frameworks)}] {fw['name']}: "
                f"{len(current)} → {len(new_triggers)} triggers",
                file=sys.stderr,
            )

        except Exception as e:
            fail_count += 1
            print(f"  [{i}/{len(frameworks)}] {fw['name']}: ERROR {e}", file=sys.stderr)
            results.append({
                "framework_db_id": fw["id"],
                "framework_id": fw["framework_id"],
                "name": fw["name"],
                "category": fw.get("category"),
                "old_triggers": current,
                "new_triggers": current,
                "status": "failed",
            })

    if fail_count:
        print(
            f"\n  WARNING: {fail_count}/{len(frameworks)} failed — "
            f"those frameworks keep their current triggers.",
            file=sys.stderr,
        )

    return results


# ---------------------------------------------------------------------------
# Database update
# ---------------------------------------------------------------------------

def apply_updates(supabase, results: list[dict]) -> int:
    """Update when_to_apply for rewritten frameworks."""
    updated = 0
    for r in results:
        if r["status"] != "rewritten":
            continue
        try:
            supabase.table("frameworks").update(
                {"when_to_apply": r["new_triggers"]}
            ).eq("id", r["framework_db_id"]).execute()
            updated += 1
            print(f"  Updated: {r['name']}", file=sys.stderr)
        except Exception as e:
            print(f"  FAILED to update {r['name']}: {e}", file=sys.stderr)
    return updated


# ---------------------------------------------------------------------------
# Backfill trigger embeddings (replaces curl to admin endpoint)
# ---------------------------------------------------------------------------

def backfill_embeddings(
    supabase, agent_id: str, results: list[dict]
) -> int:
    """Re-embed updated triggers and write to framework_trigger_embeddings."""
    from google import genai
    from app.core.config import settings

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    embedded_count = 0

    for r in results:
        if r["status"] != "rewritten":
            continue

        fw_db_id = r["framework_db_id"]
        triggers = r["new_triggers"]

        try:
            # Embed all triggers in one batch using Gemini (KIN-467)
            resp = client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=triggers,
            )
            embeddings = [list(e.values) for e in resp.embeddings]

            # Delete existing embeddings for this framework (idempotent)
            supabase.table("framework_trigger_embeddings").delete().eq(
                "framework_db_id", fw_db_id
            ).execute()

            # Insert fresh rows
            rows = [
                {
                    "framework_db_id": fw_db_id,
                    "agent_definition_id": agent_id,
                    "trigger_text": trigger,
                    "embedding": emb,
                    "embedding_model": settings.EMBEDDING_MODEL,
                }
                for trigger, emb in zip(triggers, embeddings)
            ]
            supabase.table("framework_trigger_embeddings").insert(rows).execute()
            embedded_count += 1
            print(
                f"  Embedded: {r['name']} ({len(triggers)} triggers)",
                file=sys.stderr,
            )

        except Exception as e:
            print(f"  FAILED to embed {r['name']}: {e}", file=sys.stderr)

    return embedded_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Rewrite framework trigger phrases (KIN-443)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent-id", help="Agent definition UUID")
    group.add_argument("--agent-slug", help="Agent slug (e.g., 'nate') — resolves UUID from DB")
    parser.add_argument(
        "--output",
        default="scripts/trigger_rewrite_preview.json",
        help="Output JSON path for preview (default: scripts/trigger_rewrite_preview.json)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of frameworks to pilot (default: 20)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update the database (default: preview only)",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    parser.add_argument("--openai-key", default=os.environ.get("OPENAI_API_KEY"))
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)
    if not args.openai_key:
        print(
            "Error: OPENAI_API_KEY required — used by this script for the "
            "gpt-4o-mini trigger-rewrite step (not a platform requirement).",
            file=sys.stderr,
        )
        sys.exit(1)

    from supabase import create_client

    supabase = create_client(args.supabase_url, args.supabase_key)

    # Resolve agent slug → UUID if needed
    agent_id = args.agent_id or resolve_agent_id(supabase, args.agent_slug)

    # Step 1: Fetch and select frameworks
    print(f"Fetching frameworks for agent {agent_id}...", file=sys.stderr)
    by_category = fetch_frameworks_by_category(supabase, agent_id)
    total = sum(len(fws) for fws in by_category.values())
    print(f"Found {total} frameworks across {len(by_category)} categories", file=sys.stderr)

    if total == 0:
        print("Error: No frameworks found for this agent.", file=sys.stderr)
        sys.exit(1)

    selected = select_pilot_frameworks(by_category, count=args.count)
    print(f"\nSelected {len(selected)} pilot frameworks:", file=sys.stderr)
    for fw in selected:
        triggers = fw.get("when_to_apply") or []
        print(
            f"  [{fw.get('category', '?')}] {fw['name']} "
            f"({len(triggers)} current triggers)",
            file=sys.stderr,
        )

    # Step 2: Rewrite triggers via LLM
    print(f"\nRewriting triggers with GPT-4o-mini...", file=sys.stderr)
    results = rewrite_triggers(selected, args.openai_key)

    rewritten = [r for r in results if r["status"] == "rewritten"]
    failed = [r for r in results if r["status"] == "failed"]
    print(
        f"\nResults: {len(rewritten)} rewritten, {len(failed)} failed",
        file=sys.stderr,
    )

    # Step 3: Write preview
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nPreview written to {args.output}", file=sys.stderr)

    # Step 4: Apply if requested
    if args.apply:
        print(f"\n--- APPLYING UPDATES ---", file=sys.stderr)
        updated = apply_updates(supabase, results)
        print(f"\nUpdated {updated} frameworks in database.", file=sys.stderr)

        # Step 5: Re-embed updated triggers
        print(f"\n--- BACKFILLING EMBEDDINGS ---", file=sys.stderr)
        embedded = backfill_embeddings(supabase, agent_id, results, args.openai_key)
        print(f"\nEmbedded {embedded} frameworks ({embedded * 4} trigger vectors).", file=sys.stderr)
    else:
        print(
            f"\nPreview only — review {args.output} then re-run with --apply "
            f"to update the database.",
            file=sys.stderr,
        )

    # Print sample comparison
    if rewritten:
        print(f"\n--- SAMPLE COMPARISON ---", file=sys.stderr)
        for r in rewritten[:3]:
            print(f"\n  {r['name']} [{r['category']}]:", file=sys.stderr)
            print(f"    OLD: {r['old_triggers']}", file=sys.stderr)
            print(f"    NEW: {r['new_triggers']}", file=sys.stderr)


if __name__ == "__main__":
    main()
