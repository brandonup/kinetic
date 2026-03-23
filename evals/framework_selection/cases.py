"""
Framework selection eval — labeled test dataset.

KIN-260: confidence threshold tuning for the 4-step pipeline.

Spec ref: docs/specs/agents.md §4 (framework selection pipeline)
          docs/adr-005-agents-framework-selection.md

Dataset covers 4 query categories:
  - clear_match   : one framework clearly dominant; pipeline must select it
  - ambiguous     : 2+ frameworks compete; any of expected_framework_ids is correct
  - no_match      : general question; pipeline must return None (no injection)
  - multi_turn    : short follow-up with minimal semantic content; should not fire falsely

HOW TO USE THIS DATASET
-----------------------
These cases are designed to be run against a seeded test agent that contains
the SEED_FRAMEWORKS defined below. Load the seed agent once per eval run, then
iterate through EVAL_CASES.

See eval.py for the harness that runs and scores these cases.
"""

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Seed frameworks
# The eval agent must contain exactly these frameworks (use the upload endpoint
# or seed fixture). Cases reference these by framework_id.
# ---------------------------------------------------------------------------

SEED_FRAMEWORKS = [
    {
        "framework_id": "coordination-tax",
        "name": "Coordination Tax Diagnostic",
        "description": "Identifies where excess coordination overhead is slowing the team down and where decision rights are unclear.",
        "when_to_apply": [
            "team is moving slowly",
            "too many meetings",
            "decisions require too many approvals",
            "bottlenecks in execution",
            "cross-functional alignment is painful",
        ],
        "principles": [
            "Name the tax — quantify how many hours per week go to coordination vs. production.",
            "Trace the root cause — unclear ownership, fear of autonomy, or lack of trust.",
            "Prescribe the cure — tighter RACI, smaller teams, async-first, or DRI model.",
        ],
        "confidence": "high",
        "category": "operations",
    },
    {
        "framework_id": "strategic-narrative",
        "name": "Strategic Narrative Framework",
        "description": "Structures how a company or leader communicates vision, strategy, and change in a way that creates alignment and urgency.",
        "when_to_apply": [
            "explaining the company's direction",
            "communicating a strategic pivot",
            "building alignment across the organization",
            "presenting to the board",
            "all-hands speech or announcement",
        ],
        "principles": [
            "Start with the why — the problem the world has that makes this company necessary.",
            "Draw the contrast — the old world vs. the world you're building.",
            "Name the enemy — the incumbent approach, the entrenched belief, or the status quo.",
            "Show the path — concrete steps from here to the vision.",
        ],
        "confidence": "high",
        "category": "leadership",
    },
    {
        "framework_id": "pmf-signal",
        "name": "PMF Signal Framework",
        "description": "Triangulates product-market fit signals from multiple sources rather than relying on any single metric.",
        "when_to_apply": [
            "evaluating product-market fit",
            "deciding whether to scale or iterate",
            "retention is unclear",
            "customers say they love the product but growth is flat",
            "wondering if we have enough signal to raise a round",
        ],
        "principles": [
            "Triangulate: NPS alone is insufficient. Look for cohort retention, word-of-mouth coefficient, and sales cycle compression simultaneously.",
            "Sean Ellis test: >40% of users would be 'very disappointed' without the product.",
            "Leading vs. lagging: activation rate and time-to-value are leading indicators; retention is lagging.",
        ],
        "confidence": "high",
        "category": "product",
    },
    {
        "framework_id": "talent-density",
        "name": "Talent Density Principle",
        "description": "Argues that team output is multiplicative, not additive — one underperformer degrades the entire team, not just their own contribution.",
        "when_to_apply": [
            "hiring decisions",
            "underperformer on the team",
            "team morale is low",
            "wondering if we should keep someone",
            "performance review",
            "someone is a culture fit but a skill gap",
        ],
        "principles": [
            "A brilliant jerk poisons the team. Tolerate excellence only.",
            "Raise the bar at every hire — never lower it for speed.",
            "Generous severance is how you keep talent density high with dignity.",
        ],
        "confidence": "high",
        "category": "talent",
    },
    {
        "framework_id": "unit-economics",
        "name": "Unit Economics Review",
        "description": "Stress-tests the per-unit profitability of the business model before scaling.",
        "when_to_apply": [
            "analyzing the business model",
            "CAC and LTV",
            "contribution margin",
            "when to scale",
            "evaluating a pricing change",
            "fundraising due diligence prep",
        ],
        "principles": [
            "Know your payback period: LTV/CAC > 3:1 is the floor; <12 months payback is healthy.",
            "Separate fixed from variable: unit economics measures variable cost per customer, not overhead.",
            "Gross margin is destiny: everything else can be fixed; bad GM at scale is terminal.",
        ],
        "confidence": "high",
        "category": "finance",
    },
    {
        "framework_id": "decision-quality",
        "name": "Decision Quality Framework",
        "description": "Separates good decisions from good outcomes — focuses process on the quality of reasoning, not the result.",
        "when_to_apply": [
            "making a big decision",
            "reviewing a decision in hindsight",
            "should we do this",
            "high-stakes choice with uncertainty",
            "team is stuck deciding",
        ],
        "principles": [
            "Distinguish reversible from irreversible: spend more time on irreversible decisions.",
            "Pre-mortem before committing: what would have to be true for this to fail?",
            "Separate signal from noise: bad outcomes don't always mean bad decisions.",
        ],
        "confidence": "medium",
        "category": "strategy",
    },
    {
        "framework_id": "customer-discovery",
        "name": "Customer Discovery Protocol",
        "description": "Structures customer conversations to extract insights rather than confirm existing hypotheses.",
        "when_to_apply": [
            "talking to customers",
            "understanding why customers churn",
            "validating a new feature idea",
            "building a persona",
            "customer interview",
            "user research",
        ],
        "principles": [
            "Ask about their past behavior, not their future intentions.",
            "Never pitch during discovery — the moment you sell, learning stops.",
            "Follow the pain: when they mention a problem, go deeper before moving on.",
        ],
        "confidence": "high",
        "category": "product",
    },
    {
        "framework_id": "okr-cascade",
        "name": "OKR Cascade",
        "description": "Links company-level objectives to team and individual key results to ensure strategic alignment without micromanagement.",
        "when_to_apply": [
            "setting goals",
            "quarterly planning",
            "OKRs",
            "team is misaligned on priorities",
            "everyone is busy but nothing strategic is getting done",
        ],
        "principles": [
            "Objectives are directional and qualitative; key results are measurable.",
            "Cascade down, not up: company OKRs should be the constraint, not the sum of individual OKRs.",
            "60–70% attainment is the target: 100% means the bar was too low.",
        ],
        "confidence": "medium",
        "category": "strategy",
    },
]


# ---------------------------------------------------------------------------
# Eval case dataclass
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    query: str
    category: Literal["clear_match", "ambiguous", "no_match", "multi_turn"]
    expected_framework_ids: list[str]  # empty list = no match expected
    notes: str = ""
    # For multi-turn: the prior messages that provide context (not fed to framework selector)
    prior_messages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Eval dataset — 40 cases
# ---------------------------------------------------------------------------

EVAL_CASES: list[EvalCase] = [

    # -----------------------------------------------------------------------
    # Clear single-framework matches (14 cases)
    # -----------------------------------------------------------------------

    EvalCase(
        query="We keep having all-hands syncs that nobody finds useful. What's going on?",
        category="clear_match",
        expected_framework_ids=["coordination-tax"],
        notes="Meeting overhead is a textbook coordination-tax symptom.",
    ),
    EvalCase(
        query="Every decision seems to require sign-off from three different VPs before anything moves.",
        category="clear_match",
        expected_framework_ids=["coordination-tax"],
        notes="Approval chain bottleneck → coordination tax.",
    ),
    EvalCase(
        query="How should I frame the company pivot when I talk to the all-hands next week?",
        category="clear_match",
        expected_framework_ids=["strategic-narrative"],
        notes="All-hands communication of a pivot is the core use case.",
    ),
    EvalCase(
        query="I need to present our new strategy to the board. How do I structure this?",
        category="clear_match",
        expected_framework_ids=["strategic-narrative"],
        notes="Board presentation of strategy.",
    ),
    EvalCase(
        query="Users love the product in interviews but month-2 retention is around 20%. Do we have PMF?",
        category="clear_match",
        expected_framework_ids=["pmf-signal"],
        notes="Retention discrepancy is the canonical PMF signal question.",
    ),
    EvalCase(
        query="Investors are asking if we have product-market fit. How do we know?",
        category="clear_match",
        expected_framework_ids=["pmf-signal"],
        notes="Direct PMF inquiry.",
    ),
    EvalCase(
        query="Our senior engineer is brilliant but nobody wants to work with him. What do we do?",
        category="clear_match",
        expected_framework_ids=["talent-density"],
        notes="Brilliant jerk scenario — canonical talent density case.",
    ),
    EvalCase(
        query="We're hiring fast. When is it okay to make a hire even if they're not quite at the bar?",
        category="clear_match",
        expected_framework_ids=["talent-density"],
        notes="Lowering the bar at speed is what talent density warns against.",
    ),
    EvalCase(
        query="Our CAC is $400 and LTV is $800. Is the business model working?",
        category="clear_match",
        expected_framework_ids=["unit-economics"],
        notes="CAC/LTV ratio question → unit economics.",
    ),
    EvalCase(
        query="When should we start scaling spend if the unit economics aren't fully proven yet?",
        category="clear_match",
        expected_framework_ids=["unit-economics"],
        notes="Scaling decision gated on unit economics.",
    ),
    EvalCase(
        query="We're stuck on whether to build this feature. Half the team thinks yes, half thinks no.",
        category="clear_match",
        expected_framework_ids=["decision-quality"],
        notes="Team stuck on a decision → decision quality.",
    ),
    EvalCase(
        query="We just launched something that flopped. How do we figure out if it was a bad decision or just bad luck?",
        category="clear_match",
        expected_framework_ids=["decision-quality"],
        notes="Outcome vs. decision quality separation.",
    ),
    EvalCase(
        query="I need to do user interviews this week. What questions should I ask?",
        category="clear_match",
        expected_framework_ids=["customer-discovery"],
        notes="Customer interview structure.",
    ),
    EvalCase(
        query="How do I structure Q3 goals so the team knows what actually matters?",
        category="clear_match",
        expected_framework_ids=["okr-cascade"],
        notes="Quarterly goal setting → OKR cascade.",
    ),

    # -----------------------------------------------------------------------
    # Ambiguous queries — 2+ frameworks compete (10 cases)
    # -----------------------------------------------------------------------

    EvalCase(
        query="We need to figure out why engineers are leaving. Do you think it's a culture problem or compensation?",
        category="ambiguous",
        expected_framework_ids=["talent-density", "coordination-tax"],
        notes="Could be talent density (culture/performance) or coordination tax (team frustration from overhead).",
    ),
    EvalCase(
        query="Revenue growth is flat. We're not sure if it's a product problem or a go-to-market problem.",
        category="ambiguous",
        expected_framework_ids=["pmf-signal", "unit-economics"],
        notes="Flat growth could mean PMF issues or unit economics/GTM efficiency.",
    ),
    EvalCase(
        query="Should we expand to a second market now or stay focused?",
        category="ambiguous",
        expected_framework_ids=["decision-quality", "unit-economics"],
        notes="Expansion decision involves both decision quality (how to decide) and unit economics (whether economics support it).",
    ),
    EvalCase(
        query="Our team says they don't know what the company is trying to accomplish.",
        category="ambiguous",
        expected_framework_ids=["strategic-narrative", "okr-cascade"],
        notes="Misalignment could be a narrative problem or a goal-setting problem.",
    ),
    EvalCase(
        query="We're raising a Series A in 3 months. What should I be focused on?",
        category="ambiguous",
        expected_framework_ids=["unit-economics", "pmf-signal"],
        notes="Series A prep requires proving both unit economics and PMF.",
    ),
    EvalCase(
        query="The team is working hard but I don't see the output I'd expect.",
        category="ambiguous",
        expected_framework_ids=["coordination-tax", "talent-density"],
        notes="Effort-to-output mismatch = coordination overhead OR talent density.",
    ),
    EvalCase(
        query="We just lost a big customer. How should we think about this?",
        category="ambiguous",
        expected_framework_ids=["customer-discovery", "pmf-signal"],
        notes="Churn event → customer discovery (learn why) or PMF signal (pattern of churn).",
    ),
    EvalCase(
        query="I want the company to move faster. What levers do I have?",
        category="ambiguous",
        expected_framework_ids=["coordination-tax", "talent-density"],
        notes="Speed issues → either coordination overhead or talent quality.",
    ),
    EvalCase(
        query="How do I get the leadership team aligned on priorities before the board meeting?",
        category="ambiguous",
        expected_framework_ids=["okr-cascade", "strategic-narrative"],
        notes="Leadership alignment could need OKR structure or a clearer narrative.",
    ),
    EvalCase(
        query="We're not sure if we should hire a VP of Sales now or wait.",
        category="ambiguous",
        expected_framework_ids=["decision-quality", "talent-density"],
        notes="Hire/no-hire timing decision with bar-setting implications.",
    ),

    # -----------------------------------------------------------------------
    # No-match queries — no framework should fire (10 cases)
    # -----------------------------------------------------------------------

    EvalCase(
        query="Can you summarize what we talked about last week?",
        category="no_match",
        expected_framework_ids=[],
        notes="Meta request — no business framework applies.",
    ),
    EvalCase(
        query="What's the weather going to be like this weekend?",
        category="no_match",
        expected_framework_ids=[],
        notes="Completely off-domain — no false positive expected.",
    ),
    EvalCase(
        query="I had a good meeting with the team today.",
        category="no_match",
        expected_framework_ids=[],
        notes="Status update with no analytical question — nothing to match.",
    ),
    EvalCase(
        query="Can you write me a thank you email to my investor?",
        category="no_match",
        expected_framework_ids=[],
        notes="Writing task with no strategic framing needed.",
    ),
    EvalCase(
        query="What does MRR stand for?",
        category="no_match",
        expected_framework_ids=[],
        notes="Definitional question — no framework applicable.",
    ),
    EvalCase(
        query="Remind me how to export a CSV from Notion.",
        category="no_match",
        expected_framework_ids=[],
        notes="Tool how-to — clearly off-domain.",
    ),
    EvalCase(
        query="Let's keep going on the plan we discussed.",
        category="no_match",
        expected_framework_ids=[],
        notes="Continuation cue with no diagnostic content.",
    ),
    EvalCase(
        query="I'm excited about next week.",
        category="no_match",
        expected_framework_ids=[],
        notes="Sentiment expression, no analytical signal.",
    ),
    EvalCase(
        query="Here's the draft of the investor update. Can you review it?",
        category="no_match",
        expected_framework_ids=[],
        notes="Document review task — no framework context needed before reading content.",
    ),
    EvalCase(
        query="How are you today?",
        category="no_match",
        expected_framework_ids=[],
        notes="Conversational opener — no framework should fire.",
    ),

    # -----------------------------------------------------------------------
    # Multi-turn follow-up queries (6 cases)
    # These queries are short and context-dependent.
    # The prior_messages field shows what came before.
    # The framework selector sees ONLY the current query + the conversation
    # history summary — it does NOT re-read prior messages in full.
    # Expected: if context is clear, the same framework continues.
    #           if query is a pure follow-up with no new signal, no match.
    # -----------------------------------------------------------------------

    EvalCase(
        query="What else should I look for?",
        category="multi_turn",
        prior_messages=[
            "User: We're seeing retention drop at week 4.",
            "Assistant: [PMF Signal Framework applied] Week 4 churn is worth triangulating...",
        ],
        expected_framework_ids=["pmf-signal"],
        notes="Follow-up in an active PMF discussion — framework should persist.",
    ),
    EvalCase(
        query="Got it. Any other examples?",
        category="multi_turn",
        prior_messages=[
            "User: Tell me about our coordination overhead.",
            "Assistant: [Coordination Tax applied] ...",
        ],
        expected_framework_ids=["coordination-tax"],
        notes="Continuation in coordination tax discussion.",
    ),
    EvalCase(
        query="Yeah.",
        category="multi_turn",
        prior_messages=[
            "User: Does this make sense?",
            "Assistant: Yes, here's the breakdown...",
        ],
        expected_framework_ids=[],
        notes="One-word affirmation — no framework should fire. High false-positive risk.",
    ),
    EvalCase(
        query="Interesting. What would you do?",
        category="multi_turn",
        prior_messages=[
            "User: We have three candidates for VP Sales.",
            "Assistant: [Talent Density applied] Here's how to think about each...",
        ],
        expected_framework_ids=["talent-density"],
        notes="Follow-on in talent density discussion.",
    ),
    EvalCase(
        query="Okay.",
        category="multi_turn",
        prior_messages=[
            "User: How do I write this email?",
            "Assistant: Here's a draft...",
        ],
        expected_framework_ids=[],
        notes="Acknowledgement to a writing task — no framework applies.",
    ),
    EvalCase(
        query="What about the other two?",
        category="multi_turn",
        prior_messages=[
            "User: Which OKR should we cut if we have to choose?",
            "Assistant: [OKR Cascade applied] Start with the one most upstream...",
        ],
        expected_framework_ids=["okr-cascade"],
        notes="Follow-up in OKR discussion — 'the other two' refers to remaining OKRs.",
    ),
]


# ---------------------------------------------------------------------------
# Sanity checks (run at import time)
# ---------------------------------------------------------------------------

_all_seed_ids = {fw["framework_id"] for fw in SEED_FRAMEWORKS}
for _case in EVAL_CASES:
    for _fid in _case.expected_framework_ids:
        assert _fid in _all_seed_ids, (
            f"Case references unknown framework_id '{_fid}': {_case.query[:60]}"
        )

assert len(EVAL_CASES) >= 30, f"Dataset has only {len(EVAL_CASES)} cases — need ≥30"
