"""
Framework Extraction Pipeline for Kinetic
==========================================

Two-pass extraction of frameworks and mental models from a thought leader's corpus.

Pass 1: Scan each post individually for frameworks/mental models.
Pass 2: Deduplicate, merge, and produce structured framework entries.

Usage:
    cd nbj_extractor

    # Test on the first 10 posts
    python extract_frameworks.py both --limit 10

    # Scale up: next 50 posts (posts 11-60), then rebuild full index
    python extract_frameworks.py both --offset 10 --limit 50

    # Run Pass 1 only (scans posts, writes raw candidates)
    python extract_frameworks.py pass1 --limit 50

    # Run Pass 2 only (deduplicates and structures from existing candidates)
    python extract_frameworks.py pass2

    # Run full corpus
    python extract_frameworks.py both

Output:
    pass1_candidates.jsonl  — raw framework candidates (one per line)
    frameworks_index.json   — final structured framework index
"""

import json
import re
import sys
import os
import time
from pathlib import Path
from difflib import SequenceMatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Falling back to environment variables.")
    print("Run: pip install python-dotenv --break-system-packages")

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed.")
    print("Run: pip install anthropic --break-system-packages")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Input file lives in the same directory as this script
INPUT_FILE = "nate_b_jones_content.jsonl"
PASS1_OUTPUT = "pass1_candidates.jsonl"
PASS2_OUTPUT = "frameworks_index.json"
PASS2_PROGRESS = "pass2_progress.jsonl"  # per-framework enrichment progress (resume support)

PASS1_MODEL = "claude-sonnet-4-6"
PASS2_MODEL = "claude-opus-4-6"

# Rate limiting — adjust if you hit API limits
PASS1_DELAY = 0.5   # seconds between Pass 1 calls
PASS2_DELAY = 3.0   # seconds between Pass 2 calls (Opus needs breathing room)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PASS1_SYSTEM = """You are an expert at identifying frameworks, mental models, and structured reasoning approaches in written content.

A "framework" is a named, reusable THINKING TOOL with structure — it has steps, principles, a matrix, a diagnostic checklist, or some other repeatable method that can be APPLIED TO DIFFERENT SITUATIONS. The key test: could someone use this framework on a completely different problem in a completely different domain? Examples: "Jobs to Be Done", "RICE scoring", "Coordination Tax Audit."

Things that ARE frameworks:
- Named diagnostic tools with structured steps ("Run this audit by doing X, then Y, then Z")
- Mental models that change how you evaluate a category of decisions
- Classification systems that help you categorize and act differently based on category
- Structured canvases or matrices for analysis

Things that are NOT frameworks — do NOT extract these:
- General advice ("be customer-centric", "start simple and iterate")
- Observations without structure ("AI is changing everything")
- Metaphors used once for illustration
- References to other people's well-known frameworks (e.g., "Porter's Five Forces") unless the author adds their own unique spin or adaptation
- Operational checklists for a specific tool or product (e.g., "safety checklist for browser automation")
- Build guides or tutorials for specific software (e.g., "how to set up a Claude Code skill")
- Recurring process templates that are just "do this every week" without a reusable reasoning structure
- Product design patterns specific to one system (e.g., "design principles for Open Brain extensions")
- Lists of tips or habits that lack a unifying analytical structure

CRITICAL — INCOMPLETE CONTENT: If a post references specific content (e.g., "12 questions", "5 rules", "the 7 steps") but that content is NOT visible in the provided text, you MUST:
1. Still extract the framework
2. Set the steps array to an EMPTY array []
3. Add a field "extraction_incomplete": true
4. Add a field "missing_content" describing what was referenced but not visible (e.g., "The post references 12 diagnostic questions but their text was not included in the provided excerpt")

Do NOT fabricate, infer, or summarize content you cannot see. An empty steps array with an incompleteness flag is vastly preferable to invented steps.

CRITICAL — NO HARDCODED MODEL NAMES: Never embed specific AI model names (e.g., "GPT-4", "Claude 3", "o3", "Gemini", "Sonnet", "Opus") in framework steps, principles, or descriptions. Instead use capability descriptions: "a model optimized for extended reasoning", "a fast model for simple classification", "your primary LLM". Frameworks must remain model-agnostic so they survive model deprecations.

CRITICAL — FRAMEWORKS vs. TEMPLATES: A framework teaches you HOW TO THINK about a problem. A prompt template tells you WHAT TO PASTE into a tool. Do NOT extract:
- Copy-paste prompt templates (e.g., "paste this system prompt into ChatGPT")
- Configuration instructions for specific tools (e.g., "set up a CLAUDE.md file with these sections")
- Step-by-step tutorials for operating software (e.g., "navigate to settings, click X, paste Y")
If the author's contribution is a reusable REASONING STRUCTURE that works across tools and contexts, extract it. If it's a literal prompt or config block, skip it.

Be SELECTIVE. Most posts do not contain an original framework. When in doubt, leave it out — Pass 2 cannot fix a noisy extraction. Return an empty array for posts with no original frameworks."""

PASS1_USER = """Analyze the following post(s) for original frameworks, mental models, or structured reasoning approaches created or significantly adapted by the author.

For each framework found, extract:
- name: The framework's name as the author uses it
- type: Classify the framework as exactly ONE of: "distinction" (two things people conflate that are actually different), "taxonomy" (classification system with named categories or tiers, including matrices), "diagnostic" (structured questions or branching logic that produces a verdict), "reframe" (challenges conventional framing of a problem), "failure_catalog" (enumerated failure modes with signals for each), "evaluation_criteria" (scoring rubric or assessment dimensions), "procedure" (sequential steps with defined outputs)
- description: One sentence explaining what it does
- when_to_apply: An array of 3-5 specific trigger situations where this framework is useful (these will be used by a classifier, so make each one a distinct, matchable condition)
- principles: Key principles or rules of the framework (as a list)
- steps: Ordered steps if the framework is procedural (as a list, or empty array if not procedural)
- source_post_id: The post ID it came from
- source_post_title: The post title
- confidence: "high" if the author explicitly names and structures it, "medium" if it's clearly a reusable model but less formally named, "low" if it's borderline

Return a JSON array. If no original frameworks are found, return [].

---

{posts}"""

PASS2_ENRICH_SYSTEM = """You are an expert at structuring knowledge frameworks for use in AI-assisted reasoning.

You will receive a single framework with its type, description, and raw extracted content. Your job is to enrich it with five fields.

---

CRITICAL AUTHORING PRINCIPLE — MODE 3:
Write all content as declarative assertions the agent reasons FROM.
NOT as instructions to the agent ("ask the user whether...").
NOT as reference material about the framework ("this framework is used to...").
The agent reads your output and already has the right lens — it doesn't need to be told what to do next.

Wrong (instruction): "First, ask the user whether they have proprietary data."
Wrong (reference): "This diagnostic is used to evaluate AI company defensibility."
Right (assertion): "Most AI products disappear when their model provider ships the same feature. Proprietary data, workflow lock-in, and regulatory moats are the only durable positions. Model-layer execution speed is not a moat."

Apply this principle to all content you generate, especially example_application.

---

FIELD 1 — core_question:
One sentence capturing the underlying question the user is wrestling with when this framework is the right lens. Write it from inside the user's perspective — the unresolved tension they feel, not a description of the framework's domain.

Good: "Is this AI company building a durable product, or just renting a position in someone else's stack?"
Bad: "Evaluating the defensibility of an AI startup's competitive moat."

---

FIELD 2 — category:
Assign exactly ONE from: competitive-positioning, strategic-planning, org-design, decision-making, ai-prompting, ai-architecture, ai-adoption, ai-governance, problem-diagnosis, product, leadership, execution, ai-evaluation

- competitive-positioning: moats, defensibility, platform risk, market position, competitive dynamics
- strategic-planning: resource allocation, opportunity sizing, prioritization, long-horizon planning
- ai-evaluation: evaluating AI system outputs, model quality, LLM pipeline performance, AI delegation readiness
- decision-making: choosing between options once the problem is understood
- problem-diagnosis: identifying and naming what is actually wrong before deciding

---

FIELD 3 — example_application:
2-3 sentences showing the framework's reasoning IN ACTION — written as if the agent is mid-conversation applying the framework. Write the INSIGHT the framework produces, not a description of the scenario.

Type-specific guidance:
- distinction: State which side of the distinction the situation falls on, and what that means. "This is X, not Y — the tell is Z."
- taxonomy: Name the category and explain what that classification implies for the decision at hand.
- diagnostic: Give the diagnostic verdict and the evidence that produced it. "The answer is X. The signals are A, B, C."
- reframe: Lead with the reframe. "The conventional read is X. That's wrong here because Y."
- failure_catalog: Name the active failure mode and the early warning that confirms it.
- evaluation_criteria: Score the dimension, name the indicator that drove the score, state the implication.
- procedure: State the output of the procedure — what the agent now knows after running through it.

Good: "The platform is renting a position. Their differentiation is a wrapper around an API that the model provider ships in every major update. The one surviving asset — their customer dataset — is real but thin: three months of usage history isn't switching cost."
Bad: "A VC firm uses this framework to evaluate an AI startup by examining their data assets and platform dependencies."

---

FIELD 4 — when_to_apply:
3-5 triggers that sound like how a real user phrases their problem. The classifier matches user queries to these — so each trigger should describe the SPECIFIC situation where THIS framework is the right choice over its category-mates. Make them discriminating, not just broadly relevant.

- Each should sound like a real question or situation: "My AI product depends on OpenAI's API and I'm worried they'll build what we do" NOT "Evaluating whether an AI startup has a defensible competitive moat"
- Mix formats: some as questions, some as situations
- Each trigger should be distinct — don't rephrase the same thing 5 ways
- Think: what situation would make someone need THIS framework and NOT the other frameworks in the same category?

Return a JSON object with exactly four keys: "core_question", "category", "example_application", "when_to_apply". Nothing else."""

PASS2_ENRICH_USER = """Enrich this framework:

Name: {name}
Type: {type}
Description: {description}
Principles: {principles}
Steps: {steps}
Current triggers: {when_to_apply}
Source post: {source_title}

Return JSON: {{"core_question": "...", "category": "...", "example_application": "...", "when_to_apply": ["...", "...", "..."]}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_posts(path: str) -> list[dict]:
    """Load all posts from the JSONL file."""
    posts = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                posts.append(json.loads(line))
    return posts


def call_llm(client, model: str, system: str, user: str, max_tokens: int = 4096, retries: int = 3) -> str:
    """Make a single API call with exponential backoff retry on overloaded errors."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        except Exception as e:
            error_str = str(e)
            is_overloaded = "529" in error_str or "overloaded" in error_str.lower()
            is_rate_limit = "429" in error_str or "rate" in error_str.lower()

            if (is_overloaded or is_rate_limit) and attempt < retries - 1:
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s
                print(f"      API overloaded/rate-limited (attempt {attempt + 1}/{retries}). Waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def extract_json_from_response(text: str) -> list | dict:
    """Extract JSON from an LLM response, handling markdown code fences and prose wrappers."""
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # If the response has prose around the JSON, find the outermost [ or {
    # Try array first (expected format), then object
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        end_idx = text.rfind(end_char)
        if end_idx == -1 or end_idx <= start_idx:
            continue
        candidate = text[start_idx:end_idx + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Nothing worked — raise with the original text for debug
    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


def format_post_for_prompt(post: dict) -> str:
    """Format a single post for inclusion in a prompt.

    Sends the FULL post content and all sections — no truncation.
    The model sees everything the author wrote so framework substance
    is never cut off regardless of where it appears in the post.
    """
    sections_text = ""
    if post.get("sections"):
        for s in post["sections"]:
            sections_text += f"\n### {s.get('heading', '')}\n{s.get('content', '')}\n"

    return f"""## Post ID: {post['id']}
**Title:** {post['title']}

{post.get('content', '')}
{sections_text}
"""


# ---------------------------------------------------------------------------
# Pass 1: Per-post scanning
# ---------------------------------------------------------------------------

def run_pass1(client, posts: list[dict]):
    """Scan each post individually for framework candidates.

    Each post gets its own API call — no batching. This ensures the model
    sees full post content and eliminates cross-post contamination.
    """
    print(f"\n{'='*60}")
    print(f"PASS 1: Scanning {len(posts)} posts for frameworks")
    print(f"{'='*60}\n")

    candidates = []
    processed = 0

    # If resuming, load existing candidates
    existing_ids = set()
    if os.path.exists(PASS1_OUTPUT):
        with open(PASS1_OUTPUT, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    c = json.loads(line)
                    existing_ids.add(c.get("source_post_id"))
                    candidates.append(c)
        print(f"Resuming: {len(candidates)} candidates from {len(existing_ids)} posts already processed.\n")

    # Open output file in append mode
    with open(PASS1_OUTPUT, "a") as out_f:
        for i, post in enumerate(posts):
            if post["id"] in existing_ids:
                continue

            _process_post(client, post, out_f, candidates)
            processed += 1

            if processed % 25 == 0:
                print(f"  Progress: {processed}/{len(posts)} posts | {len(candidates)} candidates found")

            if i < len(posts) - 1:
                time.sleep(PASS1_DELAY)

    print(f"\nPass 1 complete.")
    print(f"  Posts processed this run: {processed}")
    print(f"  Total candidates: {len(candidates)}")
    print(f"  Output: {PASS1_OUTPUT}")

    return candidates


def _process_post(client, post: dict, out_f, candidates: list):
    """Process a single post and write candidates to file."""
    post_text = format_post_for_prompt(post)

    try:
        response = call_llm(
            client,
            model=PASS1_MODEL,
            system=PASS1_SYSTEM,
            user=PASS1_USER.format(posts=post_text),
            max_tokens=8192,
        )

        # --- Truncation detection ---
        # If the response doesn't end with ] or } (ignoring whitespace),
        # it was likely cut off by the max_tokens limit.
        stripped = response.strip()
        if stripped and stripped[-1] not in (']', '}'):
            print(f"  WARNING: Response for post '{post['id']}' appears truncated "
                  f"(ends with '{stripped[-20:]}...'). May have hit max_tokens limit.")

        results = extract_json_from_response(response)

        # Handle dict-wrapped responses
        if isinstance(results, dict):
            for key in ("frameworks", "results", "data"):
                if key in results and isinstance(results[key], list):
                    results = results[key]
                    break
            else:
                if "name" in results:
                    results = [results]
                else:
                    results = []

        if isinstance(results, list):
            post_date = post.get("date", "")
            for fw in results:
                if fw and isinstance(fw, dict) and fw.get("name"):
                    fw["source_post_date"] = post_date
                    out_f.write(json.dumps(fw) + "\n")
                    out_f.flush()
                    candidates.append(fw)
                    print(f"  Found: {fw['name']} (from: {fw.get('source_post_title', 'unknown')[:50]})")

    except json.JSONDecodeError:
        print(f"  Warning: Could not parse JSON for post '{post['id']}'. Skipping.")
    except Exception as e:
        print(f"  Error processing post '{post['id']}': {e}")


# ---------------------------------------------------------------------------
# Pass 2: Deduplicate, merge, and structure
# ---------------------------------------------------------------------------

def _make_id(name: str) -> str:
    """Convert a framework name to a kebab-case ID."""
    # Replace non-alphanumeric chars with hyphens, collapse multiples, strip edges
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # Truncate to reasonable length
    return slug[:60].rstrip('-')


def _dedup_candidates(candidates: list[dict]) -> list[dict]:
    """Merge candidates that refer to the same framework (same or very similar names)."""
    groups: list[list[dict]] = []

    for candidate in candidates:
        name = candidate.get("name", "").lower()
        matched = False

        for group in groups:
            group_name = group[0].get("name", "").lower()
            similarity = SequenceMatcher(None, name, group_name).ratio()
            if similarity > 0.7:
                group.append(candidate)
                matched = True
                break

        if not matched:
            groups.append([candidate])

    # For each group, pick the highest-confidence version and merge source posts
    merged = []
    for group in groups:
        # Sort: high confidence first, then longest description
        group.sort(key=lambda c: (
            0 if c.get("confidence") == "high" else 1,
            -len(c.get("description", "")),
        ))
        best = dict(group[0])  # copy

        # Collect all source posts (with date)
        seen_posts = set()
        source_posts = []
        for c in group:
            pid = c.get("source_post_id", "")
            if pid and pid not in seen_posts:
                seen_posts.add(pid)
                source_posts.append({
                    "id": pid,
                    "title": c.get("source_post_title", ""),
                    "date": c.get("source_post_date", ""),
                })

        best["source_posts"] = source_posts
        # Derive top-level date = earliest non-empty source post date
        dates = sorted(sp["date"] for sp in source_posts if sp.get("date"))
        best["date"] = dates[0] if dates else ""
        # Remove the flat fields now that we have the array
        best.pop("source_post_id", None)
        best.pop("source_post_title", None)
        best.pop("source_post_date", None)

        merged.append(best)

    return merged


# ---------------------------------------------------------------------------
# Quality validators — run after dedup, before LLM enrichment
# ---------------------------------------------------------------------------

# Patterns that reference content without containing it (truncation artifacts)
_META_REFERENCE_PATTERNS = [
    r"work through .* questions",
    r"follow the .* steps",
    r"apply the .* (?:rules|principles|criteria)",
    r"use the .* (?:framework|model|tool|audit)",
    r"run the .* (?:diagnostic|assessment|audit)",
    r"go through .* (?:questions|prompts|items)",
    r"answer (?:the|all) .* questions",
    r"complete the .* (?:checklist|scorecard|matrix)",
]

# Signals that steps are copy-paste prompt templates, not reasoning structures
_TEMPLATE_SIGNALS = [
    r"paste (?:this|the following)",
    r"copy (?:this|the following)",
    r"use this (?:prompt|json|template|system prompt)",
    r"type the following",
    r"navigate to (?:settings|the)",
    r"open (?:chatgpt|claude|gemini|cursor|copilot|your (?:llm|ai))",
    r"run this prompt",
    r"insert (?:this|the following)",
    r"add (?:this|the following) to your",
    r"here(?:'|')s the (?:prompt|template)",
    r"set (?:the )?system prompt to",
    r"in the (?:system|user) (?:prompt|message|field)",
]

_REASONING_SIGNALS = [
    r"\bidentify\b", r"\bassess\b", r"\bdetermine\b", r"\bevaluate\b",
    r"\bclassify\b", r"\bdiagnose\b", r"\bcompare\b", r"\bprobe\b",
    r"\banalyze\b", r"\bprioritize\b", r"\bmap\b", r"\bscore\b",
    r"\baudit\b", r"\btest whether\b",
]

# Signals that steps describe a multi-phase project plan, not a conversation
_TEMPORAL_PATTERNS = [
    r"(?:month|week|day)\s*\d",
    r"phase\s*\d",
    r"over the next (?:quarter|month|year|sprint)",
    r"(?:first|second|third) quarter",
    r"(?:q[1-4])\b",
    r"sprint \d",
    r"by (?:end of|eoy|eoq)",
]

# Tool-specific CLI/config syntax that agents can't execute
_TOOL_SPECIFIC_PATTERNS = [
    r"\.claude/", r"CLAUDE\.md", r"/init\b", r"\$ARGUMENTS",
    r"\bLangGraph\b", r"\bLangChain\b", r"\bdocker\b", r"\bkubectl\b",
    r"\bgit (?:clone|push|pull|checkout)\b", r"\bnpm (?:install|run)\b",
    r"\bpip install\b", r"\bdeploy\b", r"\bCI/CD\b",
    r"\.(?:yaml|yml|toml|ini) file",
]

# Self-assessment language that creates unusable self-scoring steps
_SELF_ASSESSMENT_PATTERNS = [
    r"score yourself", r"rate yourself", r"rank yourself",
    r"assess (?:where )?you(?:r|rself)", r"reflect on your",
    r"ask yourself", r"on a (?:scale|piece) of",
    r"draw (?:a|your)", r"write down your",
    r"give yourself a",
]

# Mode 1/2 authoring voice — instructions to the LLM or encyclopedia definitions
# Mode 3 is the target: declarative assertions the LLM reasons *from*
_MODE12_PATTERNS = [
    r"^do not\b",
    r"^start (?:by|with|minimal)",
    r"^ask (?:the user|yourself)",
    r"^tell (?:the user|them)",
    r"^walk (?:the user|them)",
    r"^first,?\s+ask\b",
    r"(?:this framework|this diagnostic|this model) is used to",
    r"can be defined as\b",
]

# Hardcoded AI model names that should be capability descriptions instead
_MODEL_NAME_PATTERN = re.compile(
    r"\b(?:GPT-\d[\w.-]*|Claude[\s-]?\d[\w.-]*|Gemini[\s-]?\d[\w.-]*"
    r"|o[1-9]\b|Opus\b|Sonnet\b|Haiku\b|Perplexity\b|Mistral[\s-]?\w*"
    r"|Llama[\s-]?\d[\w.-]*|Grok[\s-]?\d[\w.-]*|DeepSeek[\s-]?\w*)",
    re.IGNORECASE,
)


def _count_matches(steps: list[str], patterns: list[str]) -> int:
    """Count how many steps match at least one pattern in the list."""
    count = 0
    for step in steps:
        step_lower = step.lower()
        for pattern in patterns:
            if re.search(pattern, step_lower):
                count += 1
                break
    return count


def _add_flag(fw: dict, defect: str, note: str):
    """Append a review flag to a framework's review_flags array."""
    fw.setdefault("review_flags", [])
    fw["review_flags"].append({
        "status": "needs_manual_review",
        "defect": defect,
        "note": note,
    })


def _run_quality_validators(frameworks: list[dict]) -> list[dict]:
    """Run all quality validators and attach review_flags to problematic frameworks.

    Validators:
      0. extraction_incomplete — Pass 1 flagged the extraction as incomplete (missing content)
      1. meta_reference_steps — steps that gesture at content without containing it
      2. literal_prompt_template — steps that are copy-paste instructions, not reasoning
      3. process_spec — steps that describe multi-phase project plans or tool-specific configs
      4. self_assessment_trap — steps that require the user to self-score (unusable by agents)
      5. hardcoded_model_names — steps/principles that embed specific AI model names
      6. mode12_content — principles written as LLM instructions or encyclopedia definitions
                          instead of declarative assertions (Mode 3)
    """
    counts = {
        "extraction_incomplete": 0,
        "meta_reference_steps": 0,
        "literal_prompt_template": 0,
        "process_spec": 0,
        "self_assessment_trap": 0,
        "hardcoded_model_names": 0,
        "mode12_content": 0,
    }

    for fw in frameworks:
        steps = fw.get("steps", [])
        principles = fw.get("principles", [])
        all_text = steps + principles
        n_steps = len(steps) if steps else 1  # avoid division by zero

        # --- Validator 0: Extraction incomplete (flagged by Pass 1) ---
        if fw.get("extraction_incomplete"):
            missing = fw.get("missing_content", "unspecified content")
            _add_flag(fw, "extraction_incomplete", (
                f"Pass 1 flagged this extraction as incomplete. "
                f"Missing: {missing}. Re-extract from full source post."
            ))
            counts["extraction_incomplete"] += 1

        # --- Validator 1: Meta-reference steps ---
        for step in steps:
            for pattern in _META_REFERENCE_PATTERNS:
                if re.search(pattern, step.lower()):
                    _add_flag(fw, "meta_reference_steps", (
                        f"Step '{step[:80]}...' references content without "
                        f"containing it. Re-extract from full source post."
                    ))
                    counts["meta_reference_steps"] += 1
                    break
            else:
                continue
            break  # one flag per framework per validator

        # --- Validator 2: Literal prompt template ---
        template_hits = _count_matches(steps, _TEMPLATE_SIGNALS)
        reasoning_hits = _count_matches(steps, _REASONING_SIGNALS)
        if (
            n_steps >= 2
            and template_hits / n_steps >= 0.5
            and reasoning_hits / n_steps < 0.25
        ):
            _add_flag(fw, "literal_prompt_template", (
                f"{template_hits}/{n_steps} steps contain template/paste language "
                f"with only {reasoning_hits} reasoning signals. "
                f"Likely a copy-paste prompt, not a reasoning framework."
            ))
            counts["literal_prompt_template"] += 1

        # --- Validator 3: Process spec / project plan ---
        temporal_hits = _count_matches(steps, _TEMPORAL_PATTERNS)
        if temporal_hits >= 2:
            _add_flag(fw, "process_spec", (
                f"{temporal_hits} steps contain temporal/phased language "
                f"(month/week/phase/quarter). Likely a project plan, not a "
                f"conversational reasoning framework."
            ))
            counts["process_spec"] += 1

        tool_hits = _count_matches(all_text, _TOOL_SPECIFIC_PATTERNS)
        if tool_hits >= 2:
            _add_flag(fw, "tool_specific_config", (
                f"{tool_hits} steps/principles contain tool-specific CLI syntax "
                f"or config references. Rewrite to tool-agnostic reasoning steps."
            ))
            counts["process_spec"] += 1

        # --- Validator 4: Self-assessment trap ---
        self_hits = _count_matches(steps, _SELF_ASSESSMENT_PATTERNS)
        if n_steps >= 2 and self_hits / n_steps >= 0.5:
            _add_flag(fw, "self_assessment_trap", (
                f"{self_hits}/{n_steps} steps use self-directed assessment "
                f"language ('score yourself', 'rate yourself'). Convert to "
                f"agent-interview format where the agent asks questions and "
                f"derives the score."
            ))
            counts["self_assessment_trap"] += 1

        # --- Validator 5: Hardcoded model names ---
        model_hits = []
        for item in all_text:
            matches = _MODEL_NAME_PATTERN.findall(item)
            model_hits.extend(matches)
        if model_hits:
            unique = sorted(set(model_hits))
            _add_flag(fw, "hardcoded_model_names", (
                f"Found hardcoded model names: {', '.join(unique)}. "
                f"Replace with capability descriptions "
                f"(e.g., 'a model optimized for extended reasoning')."
            ))
            counts["hardcoded_model_names"] += 1

        # --- Validator 6: Mode 1/2 authoring voice in principles ---
        # Quality warning only — does not trigger quarantine.
        n_principles = len(principles) if principles else 1  # avoid division by zero
        mode12_hits = _count_matches(principles, _MODE12_PATTERNS)
        if len(principles) >= 2 and mode12_hits / n_principles >= 0.5:
            _add_flag(fw, "mode12_content", (
                f"{mode12_hits}/{len(principles)} principles use Mode 1/2 authoring "
                f"voice (LLM instructions or encyclopedia definitions). "
                f"Rewrite as declarative assertions the agent reasons from, not "
                f"procedures it follows or definitions it recites."
            ))
            counts["mode12_content"] += 1

    # Print summary
    total_flagged = sum(counts.values())
    if total_flagged:
        print(f"    Quality validators flagged {total_flagged} issues:")
        for defect, count in counts.items():
            if count:
                print(f"      {defect}: {count}")
    else:
        print(f"    Quality validators: all clear.")

    return frameworks


# ---------------------------------------------------------------------------
# Auto-remediation — fix what doesn't need human review
# ---------------------------------------------------------------------------

# Map of specific model name patterns → generic capability descriptions
_MODEL_REPLACEMENTS = [
    # Extended reasoning / frontier models
    (re.compile(r"\b(?:o[1-3](?:-\w+)?|GPT-4o?\b[\w.-]*)", re.IGNORECASE),
     "a frontier reasoning model"),
    # Claude family
    (re.compile(r"\bClaude[\s-]?\d[\w.-]*\s*(?:Opus|Sonnet|Haiku)?", re.IGNORECASE),
     "a capable LLM"),
    (re.compile(r"\bOpus\b", re.IGNORECASE), "a high-capability model"),
    (re.compile(r"\bSonnet\b", re.IGNORECASE), "a balanced model"),
    (re.compile(r"\bHaiku\b", re.IGNORECASE), "a fast, lightweight model"),
    # Gemini
    (re.compile(r"\bGemini[\s-]?\d[\w.-]*", re.IGNORECASE),
     "a multimodal model"),
    # Open-source / other
    (re.compile(r"\b(?:Llama[\s-]?\d[\w.-]*|Mistral[\s-]?\w*|DeepSeek[\s-]?\w*)", re.IGNORECASE),
     "an open-weight model"),
    (re.compile(r"\bGrok[\s-]?\d[\w.-]*", re.IGNORECASE),
     "a conversational model"),
    (re.compile(r"\bPerplexity\b", re.IGNORECASE),
     "a search-augmented model"),
]


def _auto_remediate(frameworks: list[dict]) -> list[dict]:
    """Apply mechanical fixes to frameworks that don't require human judgment.

    Currently handles:
      - Replacing hardcoded model names with capability descriptions
    """
    fixed_count = 0

    for fw in frameworks:
        flags = fw.get("review_flags", [])
        has_model_flag = any(f["defect"] == "hardcoded_model_names" for f in flags)
        if not has_model_flag:
            continue

        # Replace model names in steps and principles
        changed = False
        for field in ("steps", "principles"):
            items = fw.get(field, [])
            new_items = []
            for item in items:
                original = item
                for pattern, replacement in _MODEL_REPLACEMENTS:
                    item = pattern.sub(replacement, item)
                if item != original:
                    changed = True
                new_items.append(item)
            fw[field] = new_items

        if changed:
            # Clear the hardcoded_model_names flag — it's been auto-fixed
            fw["review_flags"] = [
                f for f in flags if f["defect"] != "hardcoded_model_names"
            ]
            # Remove empty review_flags array
            if not fw["review_flags"]:
                del fw["review_flags"]
            fixed_count += 1

    if fixed_count:
        print(f"    Auto-remediated {fixed_count} frameworks (replaced hardcoded model names)")

    return frameworks


def _quarantine_flagged(frameworks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split frameworks into production-ready and quarantined lists.

    Any framework with remaining review_flags (after auto-remediation) is
    quarantined — excluded from the classifier and runtime injection until
    a human reviews and fixes it.

    Also quarantines frameworks with the legacy singular review_flag field.
    Frameworks in QUARANTINE_WHITELIST have their flags stripped and pass
    to production (manually reviewed false positives).
    """
    # Manually reviewed false positives — validators over-triggered on these.
    # process_spec: "Phase 1/2/3" are sequential thinking steps, not project timelines.
    # meta_reference_steps: referenced content exists within the same framework.
    # tool_specific_config: infrastructure vocabulary, not CLI syntax.
    QUARANTINE_WHITELIST = {
        "code-tile-chunking",
        "architecture-first-ai-coding-workflow",
        "the-architecture-of-a-prompt",
        "five-design-principles-for-context-architecture",
        "cognitive-choreography",
        "five-high-altitude-questions-for-evaluating-platform-announc",
    }

    clean = []
    quarantined = []

    for fw in frameworks:
        if fw.get("id") in QUARANTINE_WHITELIST:
            fw.pop("review_flags", None)
            fw.pop("review_flag", None)
            clean.append(fw)
            continue

        has_new_flags = bool(fw.get("review_flags"))
        has_legacy_flag = bool(fw.get("review_flag"))

        if has_new_flags or has_legacy_flag:
            quarantined.append(fw)
        else:
            clean.append(fw)

    if quarantined:
        print(f"    Quarantined {len(quarantined)} frameworks:")
        for fw in quarantined:
            defects = [f["defect"] for f in fw.get("review_flags", [])]
            if fw.get("review_flag"):
                defects.append(fw["review_flag"].get("defect", "legacy_flag"))
            print(f"      {fw['id']}: {', '.join(defects)}")

    return clean, quarantined


# ---------------------------------------------------------------------------
# Output validation — final gate before writing
# ---------------------------------------------------------------------------

# Required fields every production framework must have populated
_REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "type": str,
    "description": str,
    "when_to_apply": list,
    "principles": list,
    "category": str,
    "example_application": str,
    "source_posts": list,
}

# Fields that must be non-empty for a production framework
_NON_EMPTY_FIELDS = ["id", "name", "type", "description", "when_to_apply", "category"]


def _clean_for_output(frameworks: list[dict]) -> list[dict]:
    """Prepare frameworks for final JSON output.

    - Removes `core_question` (internal routing aid, not part of the upload schema)
    - Omits `steps` entirely when empty (schema treats steps as optional; empty list
      is semantically different from absent and would render as an empty UI section)
    """
    cleaned = []
    for fw in frameworks:
        out = {k: v for k, v in fw.items() if k != "core_question"}
        if not out.get("steps"):
            out.pop("steps", None)
        cleaned.append(out)
    return cleaned


def _validate_output(production: list[dict], quarantined: list[dict]) -> list[dict]:
    """Final validation gate before writing the output file.

    Checks:
      1. All required fields present and correctly typed
      2. Non-empty fields are populated
      3. No duplicate IDs
      4. No ID collisions between production and quarantined
    Frameworks that fail validation are moved to quarantine.
    """
    issues = 0

    # --- Check 1 & 2: Required fields and non-empty ---
    failed_ids = set()
    for fw in production:
        for field, expected_type in _REQUIRED_FIELDS.items():
            val = fw.get(field)
            if val is None:
                print(f"    VALIDATION FAIL: '{fw.get('name', '?')}' missing required field '{field}'")
                _add_flag(fw, "missing_required_field", f"Missing required field: {field}")
                failed_ids.add(fw.get("id", ""))
                issues += 1
            elif not isinstance(val, expected_type):
                print(f"    VALIDATION FAIL: '{fw.get('name', '?')}' field '{field}' has wrong type "
                      f"(expected {expected_type.__name__}, got {type(val).__name__})")
                _add_flag(fw, "wrong_field_type", f"Field '{field}' should be {expected_type.__name__}")
                failed_ids.add(fw.get("id", ""))
                issues += 1

        for field in _NON_EMPTY_FIELDS:
            val = fw.get(field)
            if val is not None and isinstance(val, (str, list)) and len(val) == 0:
                print(f"    VALIDATION FAIL: '{fw.get('name', '?')}' field '{field}' is empty")
                _add_flag(fw, "empty_required_field", f"Required field '{field}' is empty")
                failed_ids.add(fw.get("id", ""))
                issues += 1

    # --- Check 3: Duplicate IDs within production ---
    seen_ids = {}
    for fw in production:
        fid = fw.get("id", "")
        if fid in seen_ids:
            print(f"    VALIDATION FAIL: Duplicate ID '{fid}' — "
                  f"'{fw.get('name', '?')}' collides with '{seen_ids[fid]}'")
            _add_flag(fw, "duplicate_id",
                      f"ID '{fid}' already used by '{seen_ids[fid]}'")
            failed_ids.add(fid)
            issues += 1
        else:
            seen_ids[fid] = fw.get("name", "?")

    # --- Check 4: ID collisions between production and quarantined ---
    quarantined_ids = {fw.get("id", "") for fw in quarantined}
    for fid in seen_ids:
        if fid in quarantined_ids:
            print(f"    VALIDATION WARN: Production ID '{fid}' also exists in quarantine")

    # Move failed frameworks to quarantine
    if failed_ids:
        moving = [fw for fw in production if fw.get("id", "") in failed_ids]
        production = [fw for fw in production if fw.get("id", "") not in failed_ids]
        quarantined.extend(moving)
        print(f"    Moved {len(moving)} frameworks to quarantine due to validation failures")

    if issues == 0:
        print(f"    All {len(production)} production frameworks passed validation.")
    else:
        print(f"    {issues} validation issues found across {len(failed_ids)} frameworks.")

    return production


def _enrich_framework(client, fw: dict) -> dict:
    """Enrich a single framework with core_question, category, example_application, and when_to_apply.

    related_frameworks is computed deterministically in Python (Step 3) — not by the LLM.
    This eliminates the ~3,600-token other_frameworks list that was sent with every call.
    """
    try:
        response = call_llm(
            client,
            model=PASS2_MODEL,
            system=PASS2_ENRICH_SYSTEM,
            user=PASS2_ENRICH_USER.format(
                name=fw.get("name", ""),
                type=fw.get("type", "unknown"),
                description=fw.get("description", ""),
                principles=json.dumps(fw.get("principles", [])),
                steps=json.dumps(fw.get("steps", [])),
                when_to_apply=json.dumps(fw.get("when_to_apply", [])),
                source_title=fw.get("source_posts", [{}])[0].get("title", "unknown"),
            ),
            max_tokens=1200,
        )

        result = extract_json_from_response(response)

        if isinstance(result, dict):
            if "core_question" in result and isinstance(result["core_question"], str):
                fw["core_question"] = result["core_question"].strip()

            if "category" in result:
                valid_cats = {
                    "competitive-positioning", "strategic-planning", "org-design", "decision-making",
                    "ai-prompting", "ai-architecture", "ai-adoption", "ai-governance",
                    "problem-diagnosis", "product", "leadership", "execution", "ai-evaluation",
                }
                cat = result["category"].lower().strip()
                if cat in valid_cats:
                    fw["category"] = cat
                else:
                    print(f"    Warning: Invalid category '{cat}' for {fw['name']}. Defaulting to 'strategic-planning'.")
                    fw["category"] = "strategic-planning"

            if "example_application" in result:
                fw["example_application"] = result["example_application"]

            if "when_to_apply" in result and isinstance(result["when_to_apply"], list):
                fw["when_to_apply"] = result["when_to_apply"]

    except Exception as e:
        print(f"    Warning: Enrichment failed for {fw.get('name', '?')}: {e}")
        fw.setdefault("category", "strategic-planning")
        fw.setdefault("example_application", "")
        fw.setdefault("core_question", "")

    return fw


def run_pass2(client, candidates: list[dict] = None):
    """Deduplicate, enrich, and structure candidates into the final framework index.

    Architecture:
      Step 1 (Python): Generate IDs, dedup by name similarity, merge source posts
      Step 2 (LLM, per-framework): Assign category + write example_application (~200 tokens each)
      Step 3 (Python): Link related_frameworks by scanning for cross-references
    """
    print(f"\n{'='*60}")
    print(f"PASS 2: Deduplicating and structuring frameworks")
    print(f"{'='*60}\n")

    # --- Load candidates ---
    if candidates is None:
        candidates = []
        with open(PASS1_OUTPUT, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    candidates.append(json.loads(line))

    print(f"  Loaded {len(candidates)} raw candidates.")

    if not candidates:
        print("  No candidates to process. Run Pass 1 first.")
        return

    # --- Step 1: Deterministic dedup and structural transforms ---
    print(f"\n  Step 1: Deduplicating and structuring...")

    # Dedup FIRST so all source posts are merged before any filtering.
    # Previously the confidence filter ran before dedup, which dropped
    # low-confidence candidates and lost their source post references.
    frameworks = _dedup_candidates(candidates)
    print(f"    After dedup: {len(frameworks)} unique frameworks")

    # Now filter: drop frameworks where the best confidence is "low"
    # (_dedup_candidates already picks the highest-confidence version)
    before_filter = len(frameworks)
    frameworks = [f for f in frameworks if f.get("confidence") in ("high", "medium")]
    dropped = before_filter - len(frameworks)
    if dropped:
        print(f"    Dropped {dropped} low-confidence frameworks after dedup")

    # Generate IDs
    for fw in frameworks:
        fw["id"] = _make_id(fw["name"])

    # Ensure all fields exist with defaults
    for fw in frameworks:
        fw.setdefault("when_to_apply", [])
        fw.setdefault("principles", [])
        fw.setdefault("steps", [])
        fw.setdefault("confidence", "medium")
        fw.setdefault("type", "")
        fw.setdefault("core_question", "")
        fw.setdefault("category", "")
        fw.setdefault("example_application", "")
        fw.setdefault("related_frameworks", [])
        fw.setdefault("origin", "extracted")
        fw.setdefault("date", "")

    # --- Step 1b: Quality validators ---
    frameworks = _run_quality_validators(frameworks)

    # --- Step 2: LLM enrichment (one call per framework) ---
    # Each call assigns category, rewrites when_to_apply, writes example_application,
    # and identifies related_frameworks using the full index as context.
    # Saves progress after each successful enrichment so we can resume on failure.

    # Load any existing enrichment progress
    enriched_cache = {}
    if os.path.exists(PASS2_PROGRESS):
        with open(PASS2_PROGRESS, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    cached = json.loads(line)
                    enriched_cache[cached.get("id")] = cached
        print(f"\n  Step 2: Resuming enrichment — {len(enriched_cache)} already done, {len(frameworks) - len(enriched_cache)} remaining...")
    else:
        print(f"\n  Step 2: Enriching {len(frameworks)} frameworks...")

    enriched_this_run = 0
    skipped = 0

    with open(PASS2_PROGRESS, "a") as progress_f:
        for i, fw in enumerate(frameworks):
            fid = fw["id"]

            # If already enriched in a previous run, restore from cache
            if fid in enriched_cache:
                frameworks[i] = enriched_cache[fid]
                skipped += 1
                continue

            # Skip enrichment for frameworks flagged by quality validators —
            # they'll be quarantined in Step 4 and don't need Opus enrichment.
            if fw.get("review_flags"):
                skipped += 1
                continue

            print(f"    [{i+1}/{len(frameworks)}] {fw['name']}...")
            fw = _enrich_framework(client, fw)
            frameworks[i] = fw

            # Save progress (only if enrichment actually populated the key fields)
            if fw.get("category") and fw.get("example_application") and fw.get("core_question"):
                progress_f.write(json.dumps(fw) + "\n")
                progress_f.flush()
                enriched_this_run += 1
            else:
                print(f"      (enrichment incomplete — will retry on next run)")

            if i < len(frameworks) - 1:
                time.sleep(PASS2_DELAY)

    print(f"    Enriched: {enriched_this_run} new, {skipped} from cache.")

    # --- Step 3: Python post-processing cleanup ---
    print(f"\n  Step 3: Post-processing cleanup...")

    # Fix 1: Strip leading number prefixes from steps ("1. Do X" → "Do X")
    step_prefix = re.compile(r'^\d+\.\s+')
    for fw in frameworks:
        fw["steps"] = [step_prefix.sub("", s) for s in fw.get("steps", [])]

    # Fix 2: Compute related_frameworks deterministically in Python.
    # Previously sent the full ~3,600-token framework index to Opus on every enrichment call.
    # Now computed from two signals: shared source posts and trigger text overlap.
    # Capped at 4 per framework (same cap as before).
    MAX_RELATED = 4
    id_to_fw = {fw["id"]: fw for fw in frameworks}

    # Signal A: shared source posts (strongest signal — same post → same conceptual territory)
    shared_post_links: dict[str, set] = {fw["id"]: set() for fw in frameworks}
    post_to_fw_ids: dict[str, list] = {}
    for fw in frameworks:
        for sp in fw.get("source_posts", []):
            pid = sp.get("id", "")
            if pid:
                post_to_fw_ids.setdefault(pid, []).append(fw["id"])
    for pid, fids in post_to_fw_ids.items():
        for a in fids:
            for b in fids:
                if a != b:
                    shared_post_links[a].add(b)

    # Signal B: trigger text overlap (SequenceMatcher similarity > 0.6 on any trigger pair)
    trigger_links: dict[str, set] = {fw["id"]: set() for fw in frameworks}
    fw_list = list(frameworks)
    for i, fw_a in enumerate(fw_list):
        triggers_a = [t.lower() for t in fw_a.get("when_to_apply", [])]
        for fw_b in fw_list[i+1:]:
            if fw_a["id"] == fw_b["id"]:
                continue
            triggers_b = [t.lower() for t in fw_b.get("when_to_apply", [])]
            found = False
            for ta in triggers_a:
                for tb in triggers_b:
                    if SequenceMatcher(None, ta, tb).ratio() > 0.6:
                        found = True
                        break
                if found:
                    break
            if found:
                trigger_links[fw_a["id"]].add(fw_b["id"])
                trigger_links[fw_b["id"]].add(fw_a["id"])

    # Merge signals: shared posts first (stronger), then trigger overlap, cap at MAX_RELATED
    for fw in frameworks:
        fid = fw["id"]
        related = list(shared_post_links.get(fid, set()))
        for rid in trigger_links.get(fid, set()):
            if rid not in related:
                related.append(rid)
        fw["related_frameworks"] = sorted(related[:MAX_RELATED])

    computed_links = sum(len(fw.get("related_frameworks", [])) for fw in frameworks)
    print(f"    Computed {computed_links} related-framework links (shared posts + trigger overlap).")

    # Fix 3: Deduplicate when_to_apply triggers across all frameworks
    # If the same trigger text appears in multiple frameworks, keep it only
    # in the higher-confidence framework; remove from the lower-confidence one.
    seen_triggers: dict[str, str] = {}  # trigger_text → framework_id that owns it
    conf_rank = {"high": 0, "medium": 1, "low": 2}

    for fw in frameworks:
        fw_conf = conf_rank.get(fw.get("confidence", "low"), 2)
        unique = []
        for trigger in fw.get("when_to_apply", []):
            key = trigger.strip().lower()
            if key not in seen_triggers:
                seen_triggers[key] = fw["id"]
                unique.append(trigger)
            else:
                owner_id = seen_triggers[key]
                owner_fw = next((f for f in frameworks if f["id"] == owner_id), None)
                owner_conf = conf_rank.get(owner_fw.get("confidence", "low"), 2) if owner_fw else 2
                if fw_conf < owner_conf:
                    # Current framework has higher confidence — take ownership, drop from owner later
                    seen_triggers[key] = fw["id"]
                    unique.append(trigger)
                # else: duplicate in a lower/equal-confidence framework — drop it
        fw["when_to_apply"] = unique

    dupe_count = sum(
        1 for fw in frameworks
        for t in fw.get("when_to_apply", [])
        if t.strip().lower() in seen_triggers and seen_triggers[t.strip().lower()] != fw["id"]
    )
    print(f"    Steps prefixes stripped, duplicate triggers removed.")

    # Fix 4a: Explicitly remove named frameworks that are duplicates or superseded
    REMOVE_IDS = {
        "ai-exponential-fluency-assessment",  # duplicate of ai-fluency-assessment-framework
    }
    removed = [fw["id"] for fw in frameworks if fw["id"] in REMOVE_IDS]
    if removed:
        frameworks = [fw for fw in frameworks if fw["id"] not in REMOVE_IDS]
        for fw in frameworks:
            fw["related_frameworks"] = [
                rid for rid in fw.get("related_frameworks", [])
                if rid not in REMOVE_IDS
            ]
        print(f"    Explicitly removed {len(removed)} framework(s): {removed}")

    # Fix 4: Merge known sub-component frameworks into their parent
    # Five Harness Divergence Dimensions → Harness Decision Audit
    MERGE_RULES = {
        "five-harness-divergence-dimensions": "harness-decision-audit",
    }
    for child_id, parent_id in MERGE_RULES.items():
        child = next((fw for fw in frameworks if fw["id"] == child_id), None)
        parent = next((fw for fw in frameworks if fw["id"] == parent_id), None)
        if child and parent:
            # Merge unique principles
            existing = set(parent.get("principles", []))
            for p in child.get("principles", []):
                if p not in existing:
                    parent["principles"].append(p)
            # Merge unique when_to_apply triggers
            existing_triggers = set(t.strip().lower() for t in parent.get("when_to_apply", []))
            for t in child.get("when_to_apply", []):
                if t.strip().lower() not in existing_triggers:
                    parent["when_to_apply"].append(t)
            # Merge source_posts
            existing_pids = set(sp["id"] for sp in parent.get("source_posts", []))
            for sp in child.get("source_posts", []):
                if sp["id"] not in existing_pids:
                    parent["source_posts"].append(sp)
            # Remove child from index
            frameworks = [fw for fw in frameworks if fw["id"] != child_id]
            # Clean up any references to the child in other frameworks' related_frameworks
            for fw in frameworks:
                if child_id in fw.get("related_frameworks", []):
                    fw["related_frameworks"] = [
                        parent_id if rid == child_id else rid
                        for rid in fw["related_frameworks"]
                    ]
                    # Deduplicate in case parent was already listed
                    fw["related_frameworks"] = sorted(set(fw["related_frameworks"]))
            print(f"    Merged '{child_id}' into '{parent_id}'")

    # Fix 5 removed: "no steps + medium confidence" filter was based on the old
    # uniform schema where all frameworks were expected to have steps. The type-aware
    # schema includes types (distinction, taxonomy, reframe, failure_catalog,
    # evaluation_criteria) that are legitimately stepless. Thinness is caught by the
    # quality validators (self-assessment, template, process-spec, classifier magnet,
    # no agent-applicable reasoning) which are type-agnostic. Medium confidence already
    # applies a tiebreaker penalty in the selection pipeline — no hard drop needed.

    # Fix 6: related_frameworks cap and self-reference removal are now handled in Fix 2
    # (computed deterministically — no separate cleanup step needed)

    # Fix 7: Split ai-deployment into sub-categories
    AI_SUBCATEGORIES = {
        # Prompting and context design
        "four-disciplines-of-prompting": "ai-prompting",
        "system-prompts-as-onboarding-documents": "ai-prompting",
        "the-steering-audit": "ai-prompting",
        # Agent architecture and scaling
        "planner-worker-judge-pattern": "ai-architecture",
        "six-rules-for-scaling-agents": "ai-architecture",
        "delegation-vs-coordination-workflow-audit": "ai-architecture",
        "colleague-vs-tool-ai-shape-assessment": "ai-architecture",
        # Organizational AI adoption and workforce
        "the-five-levels-of-ai-assisted-development": "ai-adoption",
        "the-201-gap-framework": "ai-adoption",
        "frontier-operations": "ai-adoption",
        "context-capacity-framework-for-human-ai-complementarity": "ai-adoption",
        "five-supervisory-skills-for-ai-assisted-building": "ai-adoption",
        # Deployment safety and governance
        "intent-engineering": "ai-governance",
        "agent-deployment-kit-four-pre-flight-prompts": "ai-governance",
        "the-70-30-delegation-rule": "ai-governance",
        "rejection-as-competency": "ai-governance",
    }
    recategorized = 0
    for fw in frameworks:
        if fw["id"] in AI_SUBCATEGORIES:
            fw["category"] = AI_SUBCATEGORIES[fw["id"]]
            recategorized += 1
    if recategorized:
        print(f"    Split ai-deployment into sub-categories ({recategorized} frameworks recategorized)")

    # --- Step 4: Auto-remediation and quarantine ---
    print(f"\n  Step 4: Auto-remediation and quarantine...")
    frameworks = _auto_remediate(frameworks)
    production, quarantined = _quarantine_flagged(frameworks)

    # --- Step 5: Output validation gate ---
    print(f"\n  Step 5: Output validation...")
    production = _validate_output(production, quarantined)

    # --- Write output ---
    output = {
        "source": "nate_b_jones",
        "extraction_date": time.strftime("%Y-%m-%d"),
        "total_posts_scanned": len(set(
            c.get("source_post_id", "") for c in candidates
        )),
        "total_frameworks": len(production),
        "total_quarantined": len(quarantined),
        "frameworks": _clean_for_output(production),
        "quarantined": quarantined,
    }

    with open(PASS2_OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    # Check if all production frameworks were successfully enriched
    unenriched = [fw for fw in production if not fw.get("category") or not fw.get("example_application")]
    if unenriched:
        print(f"\nPass 2 complete (with gaps).")
        print(f"  Production frameworks: {len(production)} ({len(unenriched)} need re-enrichment)")
        print(f"  Run `python extract_frameworks.py pass2` again to retry failed enrichments.")
    else:
        print(f"\nPass 2 complete.")
        # All enrichments succeeded — clean up progress file
        if os.path.exists(PASS2_PROGRESS):
            os.rename(PASS2_PROGRESS, PASS2_PROGRESS + ".bak")
            print(f"  Progress file archived to {PASS2_PROGRESS}.bak")

    print(f"  Production frameworks: {len(production)}")
    print(f"  Quarantined frameworks: {len(quarantined)}")
    print(f"  Output: {PASS2_OUTPUT}")

    print(f"\n{'='*60}")
    print("FRAMEWORK INDEX SUMMARY")
    print(f"{'='*60}")
    for fw in production:
        conf = fw.get("confidence", "?")
        cat = fw.get("category", "?")
        name = fw.get("name", "Unnamed")
        desc = fw.get("description", "")[:80]
        sources = len(fw.get("source_posts", []))
        print(f"  [{conf}] [{cat}] {name} ({sources} sources)")
        print(f"         {desc}")

    if quarantined:
        print(f"\n{'='*60}")
        print("QUARANTINED (excluded from production)")
        print(f"{'='*60}")
        for fw in quarantined:
            defects = [f["defect"] for f in fw.get("review_flags", [])]
            if fw.get("review_flag"):
                defects.append(fw["review_flag"].get("defect", "legacy"))
            print(f"  {fw.get('name', 'Unnamed')}: {', '.join(defects)}")

    return production


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("pass1", "pass2", "both"):
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    # Parse optional --limit flag (e.g. --limit 50)
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        try:
            limit = int(sys.argv[idx + 1])
            print(f"Limit set: processing first {limit} posts only.")
        except (IndexError, ValueError):
            print("Error: --limit requires a number (e.g. --limit 50)")
            sys.exit(1)

    # Parse optional --offset flag (e.g. --offset 10 --limit 50 → posts 11-60)
    offset = 0
    if "--offset" in sys.argv:
        idx = sys.argv.index("--offset")
        try:
            offset = int(sys.argv[idx + 1])
            print(f"Offset set: skipping first {offset} posts.")
        except (IndexError, ValueError):
            print("Error: --offset requires a number (e.g. --offset 10)")
            sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        print("Add it to .env or run: export ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    client = anthropic.Anthropic()

    if mode in ("pass1", "both"):
        posts = load_posts(INPUT_FILE)
        if offset:
            posts = posts[offset:]
        if limit:
            posts = posts[:limit]
        if offset or limit:
            total = len(load_posts(INPUT_FILE))
            start = offset + 1
            end = min(offset + (limit or len(posts)), total)
            print(f"Loaded {len(posts)} posts (posts {start}-{end} of {total} total).\n")
        candidates = run_pass1(client, posts)

    if mode in ("pass2", "both"):
        candidates_arg = candidates if mode == "both" else None
        run_pass2(client, candidates_arg)


if __name__ == "__main__":
    main()