"""
Framework Enrichment Pipeline for Kinetic
==========================================

Three-pass enrichment of curated frameworks based on research findings.

Pass 1: Add `do_not_use_when` non-applicability conditions (Sonnet)
Pass 2: Rewrite `description` as model-addressed instruction (Sonnet)
Pass 3: Add "why this step matters" annotations to procedural steps (Opus)

Each pass processes one framework per API call for maximum quality.
Progress is saved after every framework — safe to interrupt and resume.

Usage:
    cd nbj_extractor

    # Run a single pass
    python enrich_frameworks.py pass1
    python enrich_frameworks.py pass2
    python enrich_frameworks.py pass3

    # Dry run — process first 5 only, print results, don't save
    python enrich_frameworks.py pass1 --dry-run --limit 5

    # Resume after interruption (skips already-enriched frameworks)
    python enrich_frameworks.py pass1

    # Force re-run on all frameworks (ignores existing enrichment)
    python enrich_frameworks.py pass1 --force

    # Run all three passes sequentially
    python enrich_frameworks.py all

Input:
    frameworks_curated.json     — 184 ICP-relevant frameworks
    nate_b_jones_content.jsonl  — source post content (Pass 3 only)

Output:
    frameworks_enriched.json    — enriched frameworks (builds incrementally)
"""

import json
import sys
import os
import time
import argparse
import copy
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Falling back to environment variables.")

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed.")
    print("Run: pip install anthropic --break-system-packages")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_FILE = "frameworks_curated.json"
OUTPUT_FILE = "frameworks_enriched.json"
CONTENT_FILE = "nate_b_jones_content.jsonl"

SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-6"

SONNET_DELAY = 0.5  # seconds between Sonnet calls
OPUS_DELAY = 2.0    # seconds between Opus calls

MAX_RETRIES = 3
RETRY_DELAY = 5.0   # seconds before retry on API error

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PASS1_SYSTEM = """You are an expert in cognitive framework design for AI advisory systems. You produce precise, structured JSON output."""

PASS1_USER = """Below is a framework that an AI agent uses when advising business leaders. The agent selects this framework based on trigger-phrase similarity to the user's query. Your job is to write NON-APPLICABILITY conditions — situations that LOOK similar to this framework's trigger conditions but are actually NOT good applications of it.

These conditions will be shown to the AI agent alongside the framework so it knows when NOT to apply the framework even if trigger similarity is high.

<framework>
Name: {name}
Type: {type}
Category: {category}
Description: {description}
Triggers (when_to_apply): {when_to_apply}
Principles: {principles}
</framework>

Write 3-4 non-applicability conditions. Each should:
- Describe a situation that could plausibly match the trigger phrases but where this framework would give bad or irrelevant advice
- Be written as a short sentence describing the user's situation (not as a rule)
- Be specific enough to be useful — "the user's question is too vague" is not helpful
- Be concise: 1 sentence, under 25 words. State the situation and why it's a mismatch. No elaboration.

Think about: adjacent domains where a different lens is needed, situations where the framework's assumptions don't hold, scale or context mismatches, and cases where the framework would over-complicate a simple question.

Return ONLY a JSON array of 3-4 strings. No commentary, no markdown fences."""

PASS2_SYSTEM = """You are writing operational instructions for an AI advisory agent named Nate. Nate advises tech founders, AI consultants, and SMB leaders navigating technology disruption. You produce concise, direct instructions."""

PASS2_USER = """Below is a framework that gets injected into Nate's context when a user's query matches its triggers. Currently the description is a passive summary — it describes what the framework IS. You need to rewrite it as a direct instruction that tells Nate how to USE the framework.

<framework>
Name: {name}
Type: {type}
Category: {category}
Current description: {description}
Triggers: {when_to_apply}
Principles: {principles}
Steps: {steps}
Non-applicability: {do_not_use_when}
</framework>

Rewrite the description as a 2-4 sentence instruction addressed directly to the agent ("You use..." / "Apply..." / "When a user..."). Follow these rules:

1. First sentence: what the framework does and when to apply it, written as an instruction.
2. Remaining sentences: HOW to apply it — what the agent should actually DO with this framework in the conversation.

The "how to apply" depends on the framework type:
- For diagnostic/procedure types that have steps: do NOT restate the steps — the steps are already in the framework. Instead focus on what the agent should push back on, what the common user blind spot is, and what this framework reveals that generic advice would miss. "Challenge the user's assumption that..." or "Push them to prove..."
- For taxonomy types: "Classify the user's situation into..." or "Sort their claims using..."
- For reframe types: "Shift the user's framing from X to Y by..." or "Challenge the assumption that..."
- For distinction types: "Help the user see the difference between X and Y by..." or "Test whether their situation is X or Y by asking..."
- For failure_catalog types: "Check the user's situation against these failure modes..." or "Look for signals of..."
- For evaluation_criteria types: "Evaluate using these criteria..." or "Score the user's situation against..."

3. Use Nate's specific vocabulary from the principles — don't genericize. If the framework talks about "middleware trap" or "three-layer test," use those exact terms.
4. Keep it under 60 words. Tight, direct, no filler.
5. Do NOT use emphatic language (no "CRITICAL", no "ALWAYS", no caps for emphasis). Calm and direct.

Return ONLY the rewritten description string. No JSON wrapper, no quotes, no commentary."""

PASS3_SYSTEM = """You are annotating procedural steps for an AI advisory agent. Your annotations must be grounded in the thought leader's actual reasoning from the source material, not generic rationale. You produce precise JSON output."""

PASS3_USER = """Each step in the framework below needs a "why this matters" annotation — a short explanation of WHY the step exists and what it reveals, distinguishes, or prevents.

The annotations must come from the thought leader's actual reasoning. Use the source material below to ground each annotation.

<framework>
Name: {name}
Description: {description}
Steps:
{steps_numbered}
Principles: {principles}
Example application: {example_application}
</framework>

<source_material>
{source_content}
</source_material>

For each step, add a "why" annotation following this pattern:
"[Original step text]. This matters because [specific rationale grounded in the source material]."

Rules:
1. The "why" must be specific to THIS step, not a generic statement about the framework.
2. Ground the rationale in the source material or principles — what does the author say about why this matters?
3. The annotation should explain what the step REVEALS or DISTINGUISHES — what would you miss if you skipped it?
4. Keep each annotation to 1-2 sentences. Tight.
5. Preserve the original step text exactly. Only append the "This matters because..." annotation.
6. If the source material doesn't contain clear rationale for a specific step, derive it from the principles and example application — but flag it with "(inferred)" at the end.

Return a JSON array of strings — the annotated steps in the same order as the input. No commentary, no markdown fences."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

client = anthropic.Anthropic()


def call_api(model: str, system: str, user: str, retries: int = MAX_RETRIES) -> str:
    """Call the Anthropic API with retries."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text.strip()
        except anthropic.RateLimitError:
            wait = RETRY_DELAY * (attempt + 1)
            print(f"    Rate limited. Waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIError as e:
            if attempt < retries - 1:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"    API error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Failed after {retries} retries")


def parse_json_array(text: str) -> list:
    """Parse a JSON array from LLM output, handling markdown fences."""
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def load_source_posts() -> dict:
    """Load source post content keyed by post ID."""
    posts = {}
    content_path = Path(CONTENT_FILE)
    if not content_path.exists():
        print(f"Warning: {CONTENT_FILE} not found. Pass 3 annotations will lack source context.")
        return posts
    with open(content_path) as f:
        for line in f:
            post = json.loads(line)
            posts[str(post["id"])] = post.get("content", "")
    print(f"  Loaded {len(posts)} source posts")
    return posts


def load_data() -> dict:
    """Load enriched file if it exists, otherwise copy from curated input."""
    output_path = Path(OUTPUT_FILE)
    if output_path.exists():
        with open(output_path) as f:
            data = json.load(f)
        print(f"  Resuming from {OUTPUT_FILE} ({data['total_frameworks']} frameworks)")
        return data

    input_path = Path(INPUT_FILE)
    if not input_path.exists():
        print(f"Error: {INPUT_FILE} not found.")
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)
    print(f"  Starting fresh from {INPUT_FILE} ({data['total_frameworks']} frameworks)")
    return data


def save_data(data: dict) -> None:
    """Save enriched data to output file."""
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def format_list(items: list) -> str:
    """Format a list as a bullet string for prompt injection."""
    return "\n".join(f"- {item}" for item in items)


def format_numbered(items: list) -> str:
    """Format a list as numbered items."""
    return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))


# ---------------------------------------------------------------------------
# Pass 1: do_not_use_when
# ---------------------------------------------------------------------------

def run_pass1(data: dict, dry_run: bool = False, limit: int = None, force: bool = False) -> dict:
    """Add do_not_use_when conditions to all frameworks."""
    frameworks = data["frameworks"]
    total = len(frameworks) if limit is None else min(limit, len(frameworks))

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Pass 1: do_not_use_when ({total} frameworks, Sonnet)")
    print("=" * 60)

    processed = 0
    skipped = 0

    for i, fw in enumerate(frameworks[:total]):
        # Skip if already enriched (unless --force)
        if not force and fw.get("do_not_use_when"):
            skipped += 1
            continue

        prompt = PASS1_USER.format(
            name=fw["name"],
            type=fw["type"],
            category=fw.get("category", ""),
            description=fw["description"],
            when_to_apply=format_list(fw.get("when_to_apply", [])),
            principles=format_list(fw.get("principles", [])),
        )

        print(f"  [{i+1}/{total}] {fw['name']}")

        if dry_run:
            print(f"    Would call Sonnet with ~{len(prompt)//4} input tokens")
            continue

        raw = call_api(SONNET_MODEL, PASS1_SYSTEM, prompt)

        try:
            conditions = parse_json_array(raw)
            if not isinstance(conditions, list) or not all(isinstance(c, str) for c in conditions):
                raise ValueError("Expected array of strings")
            fw["do_not_use_when"] = conditions
            processed += 1
            print(f"    Added {len(conditions)} conditions")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"    PARSE ERROR: {e}")
            print(f"    Raw output: {raw[:200]}")
            fw["_pass1_error"] = str(e)
            fw["_pass1_raw"] = raw

        # Save after every framework
        if not dry_run:
            save_data(data)

        time.sleep(SONNET_DELAY)

    print(f"\nPass 1 complete. Processed: {processed}, Skipped: {skipped}")
    if not dry_run:
        # Count errors
        errors = sum(1 for fw in frameworks[:total] if fw.get("_pass1_error"))
        if errors:
            print(f"  Errors: {errors} (search for _pass1_error in output file)")
    return data


# ---------------------------------------------------------------------------
# Pass 2: description rewrite
# ---------------------------------------------------------------------------

def run_pass2(data: dict, dry_run: bool = False, limit: int = None, force: bool = False) -> dict:
    """Rewrite descriptions as model-addressed instructions."""
    frameworks = data["frameworks"]
    total = len(frameworks) if limit is None else min(limit, len(frameworks))

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Pass 2: description rewrite ({total} frameworks, Sonnet)")
    print("=" * 60)

    processed = 0
    skipped = 0

    for i, fw in enumerate(frameworks[:total]):
        # Skip if already rewritten (unless --force)
        if not force and fw.get("description_original"):
            skipped += 1
            continue

        steps_str = format_numbered(fw["steps"]) if fw.get("steps") else "None — this is a conceptual framework without procedural steps"
        dnu = format_list(fw["do_not_use_when"]) if fw.get("do_not_use_when") else "Not yet defined"

        prompt = PASS2_USER.format(
            name=fw["name"],
            type=fw["type"],
            category=fw.get("category", ""),
            description=fw["description"],
            when_to_apply=format_list(fw.get("when_to_apply", [])),
            principles=format_list(fw.get("principles", [])),
            steps=steps_str,
            do_not_use_when=dnu,
        )

        print(f"  [{i+1}/{total}] {fw['name']}")

        if dry_run:
            print(f"    Would call Sonnet with ~{len(prompt)//4} input tokens")
            continue

        raw = call_api(SONNET_MODEL, PASS2_SYSTEM, prompt)

        # Output is a plain string, not JSON
        new_desc = raw.strip().strip('"').strip("'")

        if len(new_desc) < 20:
            print(f"    SUSPICIOUSLY SHORT: '{new_desc}'")
            fw["_pass2_error"] = "Output too short"
            fw["_pass2_raw"] = raw
        else:
            # Preserve original
            if not fw.get("description_original"):
                fw["description_original"] = fw["description"]
            fw["description"] = new_desc
            processed += 1
            word_count = len(new_desc.split())
            print(f"    Rewritten ({word_count} words)")
            if word_count > 75:
                print(f"    WARNING: Over 60-word target ({word_count} words)")

        if not dry_run:
            save_data(data)

        time.sleep(SONNET_DELAY)

    print(f"\nPass 2 complete. Processed: {processed}, Skipped: {skipped}")
    if not dry_run:
        errors = sum(1 for fw in frameworks[:total] if fw.get("_pass2_error"))
        if errors:
            print(f"  Errors: {errors} (search for _pass2_error in output file)")
    return data


# ---------------------------------------------------------------------------
# Pass 3: step annotations
# ---------------------------------------------------------------------------

def run_pass3(data: dict, dry_run: bool = False, limit: int = None, force: bool = False) -> dict:
    """Add 'why this step matters' annotations to procedural frameworks."""
    frameworks = data["frameworks"]
    procedural = [fw for fw in frameworks if fw.get("steps")]

    total = len(procedural) if limit is None else min(limit, len(procedural))

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Pass 3: step annotations ({total} procedural frameworks, Opus)")
    print("=" * 60)

    # Load source posts for grounding
    source_posts = load_source_posts() if not dry_run else {}

    processed = 0
    skipped = 0

    for i, fw in enumerate(procedural[:total]):
        # Skip if already annotated (unless --force)
        if not force and fw.get("steps_original"):
            skipped += 1
            continue

        # Gather source post content
        source_content_parts = []
        for sp in fw.get("source_posts", []):
            post_id = str(sp.get("id", ""))
            if post_id in source_posts:
                content = source_posts[post_id]
                # Truncate very long posts to ~2000 tokens worth
                if len(content) > 8000:
                    content = content[:8000] + "\n[... truncated for length]"
                source_content_parts.append(f"Post: {sp.get('title', 'Untitled')}\n{content}")

        source_content = "\n\n---\n\n".join(source_content_parts) if source_content_parts else "No source material available. Derive annotations from the principles and example application."

        prompt = PASS3_USER.format(
            name=fw["name"],
            description=fw["description"],
            steps_numbered=format_numbered(fw["steps"]),
            principles=format_list(fw.get("principles", [])),
            example_application=fw.get("example_application", "No example available."),
            source_content=source_content,
        )

        print(f"  [{i+1}/{total}] {fw['name']} ({len(fw['steps'])} steps)")

        if dry_run:
            has_source = bool(source_content_parts)
            print(f"    Would call Opus with ~{len(prompt)//4} input tokens (source: {'yes' if has_source else 'NO'})")
            continue

        raw = call_api(OPUS_MODEL, PASS3_SYSTEM, prompt)

        try:
            annotated = parse_json_array(raw)
            if not isinstance(annotated, list):
                raise ValueError("Expected array")
            if len(annotated) != len(fw["steps"]):
                raise ValueError(f"Expected {len(fw['steps'])} steps, got {len(annotated)}")
            if not all(isinstance(s, str) for s in annotated):
                raise ValueError("Expected array of strings")

            # Preserve originals
            if not fw.get("steps_original"):
                fw["steps_original"] = copy.deepcopy(fw["steps"])
            fw["steps"] = annotated
            processed += 1

            # Count inferred annotations
            inferred = sum(1 for s in annotated if "(inferred)" in s)
            print(f"    Annotated {len(annotated)} steps ({inferred} inferred)")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"    PARSE ERROR: {e}")
            print(f"    Raw output: {raw[:300]}")
            fw["_pass3_error"] = str(e)
            fw["_pass3_raw"] = raw

        if not dry_run:
            save_data(data)

        time.sleep(OPUS_DELAY)

    print(f"\nPass 3 complete. Processed: {processed}, Skipped: {skipped}")
    if not dry_run:
        errors = sum(1 for fw in procedural[:total] if fw.get("_pass3_error"))
        if errors:
            print(f"  Errors: {errors} (search for _pass3_error in output file)")
        inferred_total = sum(
            sum(1 for s in fw.get("steps", []) if "(inferred)" in s)
            for fw in procedural[:total]
            if fw.get("steps_original")  # only count processed ones
        )
        if inferred_total:
            print(f"  Inferred annotations: {inferred_total} (source material gaps)")
    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Enrich curated frameworks")
    parser.add_argument("pass_name", choices=["pass1", "pass2", "pass3", "all"],
                        help="Which pass to run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without calling the API")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N frameworks")
    parser.add_argument("--force", action="store_true",
                        help="Re-run on frameworks that were already enriched")
    args = parser.parse_args()

    print("Framework Enrichment Pipeline")
    print("=" * 60)

    data = load_data()

    if args.pass_name in ("pass1", "all"):
        data = run_pass1(data, dry_run=args.dry_run, limit=args.limit, force=args.force)

    if args.pass_name in ("pass2", "all"):
        # Check that Pass 1 has been run
        has_pass1 = sum(1 for fw in data["frameworks"] if fw.get("do_not_use_when"))
        if has_pass1 == 0 and args.pass_name == "pass2":
            print("\nWarning: No frameworks have do_not_use_when yet.")
            print("Run pass1 first, or pass2 will use 'Not yet defined' for non-applicability.")
            response = input("Continue anyway? [y/N] ")
            if response.lower() != "y":
                sys.exit(0)
        data = run_pass2(data, dry_run=args.dry_run, limit=args.limit, force=args.force)

    if args.pass_name in ("pass3", "all"):
        data = run_pass3(data, dry_run=args.dry_run, limit=args.limit, force=args.force)

    print("\nDone.")
    if not args.dry_run:
        # Summary stats
        fws = data["frameworks"]
        print(f"\n  Total frameworks:       {len(fws)}")
        print(f"  With do_not_use_when:   {sum(1 for fw in fws if fw.get('do_not_use_when'))}")
        print(f"  With rewritten desc:    {sum(1 for fw in fws if fw.get('description_original'))}")
        print(f"  With annotated steps:   {sum(1 for fw in fws if fw.get('steps_original'))}")
        errors = sum(1 for fw in fws if any(fw.get(f"_pass{p}_error") for p in [1, 2, 3]))
        if errors:
            print(f"  With errors:            {errors}")


if __name__ == "__main__":
    main()
