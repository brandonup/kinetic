"""
Generate framework selection eval dataset (KIN-448).

Fetches frameworks from Supabase, uses OpenAI to generate synthetic user
queries, and outputs a JSONL dataset for the eval runner.

Methods (from retrieval-accuracy-plan.md §4.1):
  1. LLM-assisted synthetic generation (~100 on-topic + ~50 adjacent)
  2. Trigger-as-query smoke test (~50 on-topic)
  3. Hand-written off-topic (~20)

Usage:
    cd packages/api
    python -m evals.framework_selection.generate_dataset \
        --agent-id <uuid> \
        --output evals/framework_selection/dataset.jsonl

Environment variables (or CLI overrides):
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY. Synthetic-query generation uses
    `gemini-2.5-flash` — no OpenAI key required (KIN-497).
"""

import argparse
import json
import os
import random
import sys


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
# Off-topic cases (Method 3 — hand-written, no DB needed)
# ---------------------------------------------------------------------------

OFF_TOPIC_CASES: list[dict] = [
    {"query": "What's the weather in Tokyo?", "expected": None, "label": "off-topic"},
    {"query": "Can you write a haiku about autumn?", "expected": None, "label": "off-topic"},
    {"query": "What's 2 + 2?", "expected": None, "label": "off-topic"},
    {"query": "How do I make chocolate chip cookies?", "expected": None, "label": "off-topic"},
    {"query": "What year was the Eiffel Tower built?", "expected": None, "label": "off-topic"},
    {"query": "Who won the Super Bowl in 2024?", "expected": None, "label": "off-topic"},
    {"query": "What's the speed of light?", "expected": None, "label": "off-topic"},
    {"query": "Translate 'hello' to Japanese.", "expected": None, "label": "off-topic"},
    {"query": "What is the boiling point of water?", "expected": None, "label": "off-topic"},
    {"query": "How many planets are in the solar system?", "expected": None, "label": "off-topic"},
    {"query": "What's the capital of France?", "expected": None, "label": "off-topic"},
    {"query": "Can you recommend a good pizza place in New York?", "expected": None, "label": "off-topic"},
    {"query": "What are the rules of chess?", "expected": None, "label": "off-topic"},
    {"query": "Who painted the Mona Lisa?", "expected": None, "label": "off-topic"},
    {"query": "How long does it take to fly from LA to London?", "expected": None, "label": "off-topic"},
    {"query": "What is photosynthesis?", "expected": None, "label": "off-topic"},
    {"query": "How do you solve a Rubik's cube?", "expected": None, "label": "off-topic"},
    {"query": "What's the tallest mountain in the world?", "expected": None, "label": "off-topic"},
    {"query": "Can you explain the plot of Inception?", "expected": None, "label": "off-topic"},
    {"query": "What is the GDP of Brazil?", "expected": None, "label": "off-topic"},
]

# ---------------------------------------------------------------------------
# LLM prompt template for synthetic generation (from plan §4.1, Method 1)
# ---------------------------------------------------------------------------

SYNTHETIC_PROMPT = """You are generating evaluation data for a retrieval system.

Framework: {name}
Description: {description}
Trigger phrases: {when_to_apply}

Generate:
1. Two natural user questions that this framework SHOULD match.
   Write them as a real person would ask — not as a keyword search,
   not repeating the trigger language. Vary vocabulary and specificity.

2. One natural user question that is TOPICALLY ADJACENT but this
   framework should NOT match. The question should be in the same
   domain but require different diagnostic reasoning.

Respond ONLY with this JSON (no markdown, no explanation):
{{"on_topic": ["q1", "q2"], "adjacent": "q3"}}"""


# ---------------------------------------------------------------------------
# Framework fetching
# ---------------------------------------------------------------------------

def fetch_frameworks_for_agent(supabase, agent_id: str) -> list[dict]:
    """Fetch frameworks that have trigger embeddings for the given agent."""
    # Get distinct framework IDs with triggers for this agent
    trigger_result = (
        supabase.table("framework_trigger_embeddings")
        .select("framework_db_id, trigger_text")
        .eq("agent_definition_id", agent_id)
        .execute()
    )
    triggers = trigger_result.data or []
    if not triggers:
        return []

    # Group trigger texts by framework ID
    trigger_map: dict[str, list[str]] = {}
    for t in triggers:
        fid = t["framework_db_id"]
        trigger_map.setdefault(fid, []).append(t["trigger_text"])

    fw_ids = list(trigger_map.keys())

    # Fetch framework details
    fw_result = (
        supabase.table("frameworks")
        .select("id, name, description, when_to_apply, category")
        .in_("id", fw_ids)
        .execute()
    )
    frameworks = fw_result.data or []

    # Attach trigger texts from embeddings
    for fw in frameworks:
        fw["_trigger_texts"] = trigger_map.get(fw["id"], [])

    return frameworks


# ---------------------------------------------------------------------------
# Synthetic generation (Method 1)
# ---------------------------------------------------------------------------

def generate_synthetic_cases(frameworks: list[dict]) -> list[dict]:
    """Generate on-topic and adjacent cases using `gemini-2.5-flash` (KIN-497)."""
    from google import genai
    from app.core.config import settings as _settings

    client = genai.Client(api_key=_settings.GEMINI_API_KEY)
    cases: list[dict] = []
    fail_count = 0

    for i, fw in enumerate(frameworks, 1):
        triggers = fw.get("when_to_apply") or []
        trigger_text = ", ".join(triggers) if isinstance(triggers, list) else str(triggers)

        prompt = SYNTHETIC_PROMPT.format(
            name=fw["name"],
            description=fw.get("description") or "(no description)",
            when_to_apply=trigger_text,
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw = (response.text or "").strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)

            for q in data.get("on_topic", []):
                cases.append({
                    "query": q,
                    "expected": fw["id"],
                    "expected_name": fw["name"],
                    "label": "on-topic",
                    "source": "synthetic",
                })

            adj = data.get("adjacent")
            if adj:
                cases.append({
                    "query": adj,
                    "expected": None,
                    "label": "adjacent",
                    "adjacent_to": fw["id"],
                    "adjacent_to_name": fw["name"],
                    "source": "synthetic",
                })

            on_count = len(data.get("on_topic", []))
            adj_count = 1 if data.get("adjacent") else 0
            print(
                f"  [{i}/{len(frameworks)}] {fw['name']}: "
                f"{on_count} on-topic, {adj_count} adjacent",
                file=sys.stderr,
            )
        except Exception as e:
            fail_count += 1
            print(f"  [{i}/{len(frameworks)}] {fw['name']}: ERROR {e}", file=sys.stderr)

    if fail_count:
        print(
            f"\n  WARNING: {fail_count} of {len(frameworks)} frameworks "
            f"failed generation — dataset may be undersized.",
            file=sys.stderr,
        )

    return cases


# ---------------------------------------------------------------------------
# Trigger-as-query smoke test (Method 2)
# ---------------------------------------------------------------------------

def generate_trigger_smoke_cases(frameworks: list[dict]) -> list[dict]:
    """Use raw trigger phrases as queries — each should match its own framework."""
    cases: list[dict] = []
    for fw in frameworks:
        # Use the embedded trigger texts (from framework_trigger_embeddings)
        trigger_texts = fw.get("_trigger_texts") or fw.get("when_to_apply") or []
        if isinstance(trigger_texts, list) and trigger_texts:
            cases.append({
                "query": trigger_texts[0],
                "expected": fw["id"],
                "expected_name": fw["name"],
                "label": "on-topic",
                "source": "trigger-smoke",
            })
    return cases


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate framework selection eval dataset (KIN-448)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent-id", help="Agent definition UUID")
    group.add_argument(
        "--agent-slug",
        help="Agent slug (e.g., 'nate') — resolves UUID from DB",
    )
    parser.add_argument(
        "--output",
        default="evals/framework_selection/dataset.jsonl",
        help="Output JSONL path (default: evals/framework_selection/dataset.jsonl)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Max frameworks to sample for synthetic generation (default: 50)",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    parser.add_argument(
        "--skip-synthetic",
        action="store_true",
        help="Skip LLM generation — only trigger smoke + off-topic",
    )
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)

    from supabase import create_client

    supabase = create_client(args.supabase_url, args.supabase_key)

    # Resolve agent slug → UUID if needed
    agent_id = args.agent_id or resolve_agent_id(supabase, args.agent_slug)

    # Fetch frameworks
    print(f"Fetching frameworks for agent {agent_id}...", file=sys.stderr)
    frameworks = fetch_frameworks_for_agent(supabase, agent_id)
    print(f"Found {len(frameworks)} frameworks with trigger embeddings", file=sys.stderr)

    if not frameworks:
        print(
            "Error: No frameworks found. Ensure the agent has frameworks with "
            "trigger embeddings (run the ADR-007 backfill).",
            file=sys.stderr,
        )
        sys.exit(1)

    all_cases: list[dict] = []

    # Method 1: LLM synthetic generation
    if not args.skip_synthetic:
        sample = frameworks
        if len(sample) > args.sample_size:
            sample = random.sample(sample, args.sample_size)
        print(
            f"\nGenerating synthetic cases for {len(sample)} frameworks...",
            file=sys.stderr,
        )
        synthetic = generate_synthetic_cases(sample)
        all_cases.extend(synthetic)
        print(f"Generated {len(synthetic)} synthetic cases", file=sys.stderr)

    # Method 2: Trigger-as-query smoke test
    print("\nGenerating trigger smoke test cases...", file=sys.stderr)
    smoke = generate_trigger_smoke_cases(frameworks)
    all_cases.extend(smoke)
    print(f"Generated {len(smoke)} smoke test cases", file=sys.stderr)

    # Method 3: Off-topic
    all_cases.extend(OFF_TOPIC_CASES)
    print(f"Added {len(OFF_TOPIC_CASES)} off-topic cases", file=sys.stderr)

    # Write JSONL
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        for case in all_cases:
            f.write(json.dumps(case) + "\n")

    # Summary
    on_topic = sum(1 for c in all_cases if c["label"] == "on-topic")
    adjacent = sum(1 for c in all_cases if c["label"] == "adjacent")
    off_topic = sum(1 for c in all_cases if c["label"] == "off-topic")
    print(f"\nDataset written to {args.output}", file=sys.stderr)
    print(
        f"Total: {len(all_cases)} cases "
        f"({on_topic} on-topic, {adjacent} adjacent, {off_topic} off-topic)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
