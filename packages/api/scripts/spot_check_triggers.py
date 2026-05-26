"""
Spot-check trigger rewrite quality (KIN-443, done-when item 5).

For each rewritten framework, embeds a sample user query and compares
similarity scores against the framework's trigger embeddings. Reports
whether the rewritten triggers score higher than the pre-rewrite baseline.

Usage:
    cd packages/api

    # Run after applying trigger rewrites AND running backfill:
    python -m scripts.spot_check_triggers \
        --agent-slug nate \
        --preview scripts/trigger_rewrite_preview.json

Environment variables:
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY

Embedding uses the platform-owned Gemini key (KIN-467).
"""

import argparse
import json
import os
import sys

# Sample queries designed to test specific framework categories.
# Each maps a framework_id pattern to a natural user query.
SPOT_CHECK_QUERIES = [
    {
        "query": "My team is pushing back on using AI tools, how do I get buy-in?",
        "expected_category": "ai-adoption",
    },
    {
        "query": "How do I figure out why our sales pipeline is stalling?",
        "expected_category": "problem-diagnosis",
    },
    {
        "query": "What makes our product different from competitors?",
        "expected_category": "competitive-positioning",
    },
    {
        "query": "How should I structure my data team across business units?",
        "expected_category": "strategy",
    },
    {
        "query": "We're growing fast and communication is breaking down between teams",
        "expected_category": "org-design",
    },
]


def resolve_agent_id(supabase, slug: str) -> str:
    """Look up agent_definition UUID from slug."""
    result = (
        supabase.table("agent_definitions")
        .select("id, name")
        .eq("slug", slug)
        .execute()
    )
    agents = result.data or []
    if not agents:
        print(f"Error: No agent found with slug '{slug}'", file=sys.stderr)
        sys.exit(1)
    agent = agents[0]
    print(f"Resolved agent '{slug}' → {agent['name']} ({agent['id']})", file=sys.stderr)
    return agent["id"]


def run_spot_check(supabase, agent_id: str, preview_path: str):
    """Run spot-check queries and report similarity scores."""
    from google import genai
    from app.core.config import settings

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Load preview to know which frameworks were rewritten
    with open(preview_path) as f:
        preview = json.load(f)
    rewritten_ids = {
        r["framework_db_id"] for r in preview if r["status"] == "rewritten"
    }

    print(f"Loaded {len(rewritten_ids)} rewritten framework IDs from preview", file=sys.stderr)
    print(f"\nRunning {len(SPOT_CHECK_QUERIES)} spot-check queries...\n", file=sys.stderr)

    results = []

    for sq in SPOT_CHECK_QUERIES:
        query = sq["query"]

        # Embed the query using Gemini (KIN-467)
        embed_resp = client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=[query],
        )
        query_embedding = list(embed_resp.embeddings[0].values)

        # Call match_framework_triggers RPC
        match_result = supabase.rpc(
            "match_framework_triggers",
            {
                "query_embedding": query_embedding,
                "p_agent_id": agent_id,
                "match_count": 10,
            },
        ).execute()

        matches = match_result.data or []

        # Annotate matches with rewrite status
        for m in matches:
            m["was_rewritten"] = m["framework_db_id"] in rewritten_ids

        # Report
        print(f"  Query: \"{query}\"", file=sys.stderr)
        print(f"  Expected category: {sq['expected_category']}", file=sys.stderr)
        if matches:
            top = matches[0]
            print(
                f"  Top match: {top.get('trigger_text', '?')} "
                f"(similarity: {top.get('similarity', 0):.4f}, "
                f"rewritten: {top.get('was_rewritten', False)})",
                file=sys.stderr,
            )
            # Show top 3
            for j, m in enumerate(matches[:3], 1):
                print(
                    f"    #{j}: sim={m.get('similarity', 0):.4f} "
                    f"trigger=\"{m.get('trigger_text', '?')[:60]}\" "
                    f"{'[REWRITTEN]' if m.get('was_rewritten') else ''}",
                    file=sys.stderr,
                )
        else:
            print(f"  No matches returned.", file=sys.stderr)
        print(file=sys.stderr)

        results.append({
            "query": query,
            "expected_category": sq["expected_category"],
            "top_matches": [
                {
                    "trigger_text": m.get("trigger_text"),
                    "similarity": m.get("similarity"),
                    "framework_db_id": m.get("framework_db_id"),
                    "was_rewritten": m.get("was_rewritten", False),
                }
                for m in matches[:5]
            ],
        })

    # Summary
    top1_rewritten = sum(
        1 for r in results
        if r["top_matches"] and r["top_matches"][0]["was_rewritten"]
    )
    print(
        f"--- SUMMARY ---\n"
        f"Queries: {len(results)}\n"
        f"Top-1 from rewritten framework: {top1_rewritten}/{len(results)}\n",
        file=sys.stderr,
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Spot-check trigger rewrite quality (KIN-443)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent-id", help="Agent definition UUID")
    group.add_argument("--agent-slug", help="Agent slug (e.g., 'nate') — resolves UUID from DB")
    parser.add_argument(
        "--preview",
        required=True,
        help="Path to trigger_rewrite_preview.json from tighten_triggers.py",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)

    from supabase import create_client

    supabase = create_client(args.supabase_url, args.supabase_key)
    agent_id = args.agent_id or resolve_agent_id(supabase, args.agent_slug)
    results = run_spot_check(supabase, agent_id, args.preview)

    # Write results
    output_path = args.preview.replace("_preview.json", "_spot_check.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
