"""
Generate KB retrieval eval dataset (KIN-449).

Fetches KB documents from Supabase, uses OpenAI to generate synthetic user
queries, and outputs a JSONL dataset for the eval runner.

Methods (from retrieval-accuracy-plan.md §1.2):
  1. Mine KB documents directly (~50 cases)
  2. Adjacent failure mode queries (~20 cases)
  3. Off-topic baseline (~10 cases)

Usage:
    cd packages/api
    python -m evals.kb_retrieval.generate_dataset \
        --scope agent_kb --scope-id <agent-uuid> \
        --output evals/kb_retrieval/dataset.jsonl

Environment variables (or CLI overrides):
    SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY
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
# Off-topic cases (hand-written, no DB needed)
# ---------------------------------------------------------------------------

OFF_TOPIC_CASES: list[dict] = [
    {"query": "What's the weather in Tokyo?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "Can you write a haiku about autumn?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "What's 2 + 2?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "How do I make chocolate chip cookies?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "Who won the Super Bowl in 2024?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "What's the speed of light?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "Translate 'hello' to Japanese.", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "What's the tallest mountain in the world?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "What are the rules of chess?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
    {"query": "How long does it take to fly from LA to London?", "should_retrieve": [], "should_not_retrieve": [], "label": "off-topic"},
]

# ---------------------------------------------------------------------------
# LLM prompt for synthetic query generation
# ---------------------------------------------------------------------------

SYNTHETIC_PROMPT = """You are generating evaluation data for a document retrieval system.

Document title: {title}
Document type: {file_type}
Content excerpt (first chunk):
{text}

Generate:
1. Two natural user questions that should retrieve content from this document.
   Write them as a real person would ask — varied vocabulary and specificity.
   Do NOT repeat the document title or use exact phrases from the text.

2. One question that is TOPICALLY ADJACENT — related domain but this
   document does NOT answer it. The question should sound plausible
   but require different information.

Respond ONLY with this JSON (no markdown, no explanation):
{{"queries": ["q1", "q2"], "adjacent": "q3"}}"""


# ---------------------------------------------------------------------------
# Document fetching
# ---------------------------------------------------------------------------

def fetch_documents_with_first_chunk(supabase, scope: str, scope_id: str) -> list[dict]:
    """Fetch KB documents with their first chunk for the given scope.

    knowledge_base_documents doesn't have project_id/agent_definition_id —
    those live on knowledge_bases. So we first find the KB(s) for the scope,
    then fetch documents belonging to those KBs.
    """
    scope_col = "project_id" if scope == "project_kb" else "agent_definition_id"

    # Step 1: Find knowledge_base(s) for this scope
    kb_result = (
        supabase.table("knowledge_bases")
        .select("id")
        .eq(scope_col, scope_id)
        .execute()
    )
    kb_ids = [kb["id"] for kb in (kb_result.data or [])]
    if not kb_ids:
        return []

    # Step 2: Fetch documents belonging to those KBs
    doc_result = (
        supabase.table("knowledge_base_documents")
        .select("id, title, file_type")
        .in_("knowledge_base_id", kb_ids)
        .is_("deleted_at", "null")
        .execute()
    )
    docs = doc_result.data or []
    if not docs:
        return []

    doc_ids = [d["id"] for d in docs]

    # Fetch first chunk of each document (chunk_index = 0)
    chunk_result = (
        supabase.table("knowledge_base_chunks")
        .select("document_id, text, chunk_index")
        .in_("document_id", doc_ids)
        .eq("chunk_index", 0)
        .execute()
    )
    chunks_by_doc = {c["document_id"]: c["text"] for c in (chunk_result.data or [])}

    # Merge
    for doc in docs:
        doc["first_chunk_text"] = chunks_by_doc.get(doc["id"], "")

    # Filter out docs without chunks
    return [d for d in docs if d["first_chunk_text"]]


# ---------------------------------------------------------------------------
# Synthetic generation (Method 1 + 2)
# ---------------------------------------------------------------------------

def generate_synthetic_cases(
    documents: list[dict], openai_key: str
) -> list[dict]:
    """Generate on-topic and adjacent cases using GPT-4o-mini."""
    import openai

    client = openai.OpenAI(api_key=openai_key)
    cases: list[dict] = []
    fail_count = 0

    for i, doc in enumerate(documents, 1):
        text_excerpt = doc["first_chunk_text"][:1500]  # Cap to avoid huge prompts

        prompt = SYNTHETIC_PROMPT.format(
            title=doc["title"],
            file_type=doc.get("file_type") or "unknown",
            text=text_excerpt,
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.8,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)

            # On-topic cases — should retrieve this document
            for q in data.get("queries", []):
                cases.append({
                    "query": q,
                    "should_retrieve": [doc["id"]],
                    "should_not_retrieve": [],
                    "label": "on-topic",
                    "source_doc_title": doc["title"],
                    "source": "synthetic",
                })

            # Adjacent case — should NOT retrieve this document
            adj = data.get("adjacent")
            if adj:
                cases.append({
                    "query": adj,
                    "should_retrieve": [],
                    "should_not_retrieve": [doc["id"]],
                    "label": "adjacent",
                    "adjacent_to_title": doc["title"],
                    "source": "synthetic",
                })

            on_count = len(data.get("queries", []))
            adj_count = 1 if adj else 0
            print(
                f"  [{i}/{len(documents)}] {doc['title'][:50]}: "
                f"{on_count} on-topic, {adj_count} adjacent",
                file=sys.stderr,
            )
        except Exception as e:
            fail_count += 1
            print(
                f"  [{i}/{len(documents)}] {doc['title'][:50]}: ERROR {e}",
                file=sys.stderr,
            )

    if fail_count:
        print(
            f"\n  WARNING: {fail_count} of {len(documents)} documents "
            f"failed generation — dataset may be undersized.",
            file=sys.stderr,
        )

    return cases


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate KB retrieval eval dataset (KIN-449)"
    )
    parser.add_argument(
        "--scope",
        choices=["project_kb", "agent_kb"],
        help="Retrieval scope: project_kb or agent_kb",
    )
    parser.add_argument("--scope-id", help="Project or agent UUID")
    parser.add_argument(
        "--agent-slug",
        help="Agent slug (e.g., 'nate') — sets scope=agent_kb and resolves UUID",
    )
    parser.add_argument(
        "--output",
        default="evals/kb_retrieval/dataset.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=30,
        help="Max documents to sample for synthetic generation (default: 30)",
    )
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    parser.add_argument("--openai-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument(
        "--skip-synthetic",
        action="store_true",
        help="Skip LLM generation, output only off-topic cases",
    )
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)
    if not args.openai_key and not args.skip_synthetic:
        print(
            "Error: OPENAI_API_KEY required (or use --skip-synthetic)",
            file=sys.stderr,
        )
        sys.exit(1)

    from supabase import create_client

    supabase = create_client(args.supabase_url, args.supabase_key)

    # Resolve agent slug → scope + scope_id
    if args.agent_slug:
        scope = "agent_kb"
        scope_id = resolve_agent_id(supabase, args.agent_slug)
    elif args.scope and args.scope_id:
        scope = args.scope
        scope_id = args.scope_id
    else:
        print(
            "Error: Provide either --agent-slug or both --scope and --scope-id",
            file=sys.stderr,
        )
        sys.exit(1)

    # Fetch documents
    print(
        f"Fetching KB documents for {scope} {scope_id}...",
        file=sys.stderr,
    )
    documents = fetch_documents_with_first_chunk(supabase, scope, scope_id)
    print(f"Found {len(documents)} documents with chunks", file=sys.stderr)

    if not documents and not args.skip_synthetic:
        print(
            "Error: No KB documents found. Ensure the scope has uploaded "
            "and ingested documents.",
            file=sys.stderr,
        )
        sys.exit(1)

    all_cases: list[dict] = []

    # Method 1+2: LLM synthetic generation
    if not args.skip_synthetic and documents:
        sample = documents
        if len(sample) > args.sample_size:
            sample = random.sample(sample, args.sample_size)
        print(
            f"\nGenerating synthetic cases for {len(sample)} documents...",
            file=sys.stderr,
        )
        synthetic = generate_synthetic_cases(sample, args.openai_key)
        all_cases.extend(synthetic)
        print(f"Generated {len(synthetic)} synthetic cases", file=sys.stderr)

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
