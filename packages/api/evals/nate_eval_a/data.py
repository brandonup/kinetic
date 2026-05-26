"""
Nate Eval A — Founder/CEO persona test dataset.

Each test case represents a realistic prompt a Founder/CEO would send to
the Nate B. Jones agent. Cases map to the four trigger situations from
``jtbd-nate-agent.md`` (§ Trigger Situations):

    1. mid-decision   — Mid-work AI decision, no strategy team
    2. stress-test    — Stress-testing an assumption before a high-stakes conversation
    3. competitive    — Diagnosing a competitive AI signal
    4. org-design     — Org/product restructuring under AI disruption

Dataset dimensions (per generate-synthetic-data skill):
    - axis_a: trigger situation (mid-decision, stress-test, competitive, org-design)
    - axis_b: decision type (build-vs-buy, moat-validity, make-vs-hire, pivot-timing)
    - axis_c: stakes (board-facing, investor-facing, internal-execution)

CONTEXT_FIXTURE
--------------
This block represents what Kinetic's persistent memory would inject for
Brandon's session. Drawn from:
    - projects/kinetic/MEMORY.md
    - memory/user_brandon_profile.md
    - projects/kinetic/docs/product/prd.md

The fixture hardcodes Brandon as the Founder/CEO test persona. In production,
Kinetic assembles this context automatically; the eval simulates that injection.
"""

# ---------------------------------------------------------------------------
# Context fixture — hardcoded company/project context for Brandon (test persona)
# ---------------------------------------------------------------------------

FOUNDER_CONTEXT_FIXTURE = """
User: Brandon Upchurch
Role: CEO and Head of Product, Son of Anton
Building: Kinetic — a context-rich AI workspace SaaS for knowledge workers
Stage: Shipping MVP. Product is live in production (kinetic-ashy-beta.vercel.app).

Company overview:
Son of Anton is a two-person GenAI product company. Brandon (CEO/Head of Product) is the
only non-technical decision-maker. The team is AI-native — the engineering agents are
AI-assisted. No dedicated strategy team. Brandon is both the strategic decision-maker and
the product lead.

Product (Kinetic):
Kinetic solves the AI cold-start problem. Every session starts from zero — the AI doesn't
know who you are, what you're working on, or what you've decided. Kinetic maintains
persistent, layered context (user → company → project → agents) and assembles it
automatically into every generation. Users build custom AI agents grounded in thought
leader corpora (uploaded writing → system prompt → framework library). MVP ships with
Active Memory + Knowledge Base. BYOK model (users bring their own API keys).

Target ICP: Tech founders, AI consultants, SMB leaders navigating AI disruption. First-wave
adopters are high-expertise users — they already have API keys and judge AI output quality
before UX polish.

Current strategic pressure points:
- AI agent tooling is commoditizing fast. Context-injection solutions (Claude Projects,
  Cursor rules, GPT memory) are shipping from well-funded competitors with distribution.
- The Nate B. Jones demo agent is Kinetic's primary proof-of-concept and launch narrative.
  It needs to be demonstrably better than ChatGPT with no context — that is the product's
  core claim.
- Brandon is prepping for early customer conversations and needs the product to prove
  the value prop on first contact.

Active memory notes:
- Kinetic prod URL: kinetic-production-b568.up.railway.app (Railway). Frontend: Vercel.
- 565+ API tests passing. TypeScript clean.
- Substack sync for Nate KB: 569 posts ingested (natesnewsletter.substack.com).
- Recency-aware retrieval shipped behind RECENCY_ENABLED flag.
""".strip()

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# Each case:
#   id:        unique identifier for the case
#   prompt:    the message the Founder/CEO sends to Nate
#   context:   injected company/project context (simulates Kinetic's memory layer)
#   trigger:   which JTBD trigger situation this maps to
#   axis_a:    trigger situation dimension
#   axis_b:    decision type dimension
#   axis_c:    stakes dimension
#   notes:     what the judge should be sensitive to for this case

TEST_CASES = [
    # --- TRIGGER 1: Mid-decision in an AI tool ---
    {
        "id": "A01",
        "prompt": (
            "I'm mid-build on Kinetic and I keep second-guessing whether persistent "
            "context is the right moat. Claude Projects, Cursor rules, and GPT memory "
            "all do some version of this now. Am I building a feature or a product?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "moat-validity",
        "axis_c": "internal-execution",
        "notes": (
            "Nate should use Brandon's specific context (Kinetic, the ICP, BYOK model) "
            "to give a diagnosis. Should NOT give a generic 'here are some ways to "
            "differentiate' menu. Should challenge or validate the moat question with "
            "specificity about Kinetic's actual position."
        ),
    },
    {
        "id": "A02",
        "prompt": (
            "Should I be building the Nate agent as a standalone product or keeping it "
            "as the demo inside Kinetic? I'm worried that Kinetic as a platform might "
            "be too abstract for early customers to get, and Nate is concrete."
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "pivot-timing",
        "axis_c": "investor-facing",
        "notes": (
            "The platform vs. persona question is a real strategic fork. Nate should "
            "give a specific verdict. Should reference that Kinetic's ICP is already "
            "identified (tech founders, AI consultants) and diagnose whether the Nate "
            "framing helps or hurts with that specific ICP."
        ),
    },
    {
        "id": "A03",
        "prompt": (
            "I'm deciding whether to build an MCP marketplace or focus purely on "
            "deepening the context stack. I have about 6 weeks of runway on current "
            "build pace before I need to show traction. What should I prioritize?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "build-vs-buy",
        "axis_c": "internal-execution",
        "notes": (
            "Runway constraint is explicit. Nate should engage with the 6-week "
            "frame directly — not give a timeless framework. Should diagnose which "
            "bet has a faster feedback loop for proving traction with the specific ICP."
        ),
    },

    # --- TRIGGER 2: Stress-testing an assumption before a high-stakes conversation ---
    {
        "id": "A04",
        "prompt": (
            "I'm talking to an early customer next week who's a solo consultant. "
            "My pitch is that Kinetic eliminates the AI cold-start problem and gives "
            "them context-persistence across every tool they use. Is that the right "
            "frame for a consultant, or am I missing what they actually care about?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "moat-validity",
        "axis_c": "investor-facing",
        "notes": (
            "Brandon is stress-testing his ICP framing before a real conversation. "
            "Nate should probe the assumption — does 'context persistence' match "
            "what a consultant's job-to-be-done actually is? Should challenge or "
            "validate with specificity, not a generic 'here are things consultants care about.'"
        ),
    },
    {
        "id": "A05",
        "prompt": (
            "I have a board check-in in two weeks and I want to frame Kinetic's "
            "differentiation around the context stack. My assumption is that persistent "
            "context is a defensible moat because it compounds — the longer a user "
            "is in Kinetic, the better their AI gets. Is that a strong enough claim?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "moat-validity",
        "axis_c": "board-facing",
        "notes": (
            "Explicit board prep. Nate should stress-test the 'compounding context' "
            "moat claim directly. Is it actually defensible? Does it require a "
            "switching cost that Kinetic's current design creates? Should be specific "
            "about what makes a moat durable versus what's just a feature."
        ),
    },
    {
        "id": "A06",
        "prompt": (
            "My hypothesis is that BYOK is a feature, not a liability — it lets me "
            "stay out of the model margin game and focus on context quality. But I'm "
            "worried it'll scare off early customers who don't want to manage API keys. "
            "Should I reconsider?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "moat-validity",
        "axis_c": "internal-execution",
        "notes": (
            "BYOK is a real Kinetic design decision. Nate should diagnose whether "
            "BYOK matches the ICP — the ICP is explicitly 'high-expertise users who "
            "already have API keys.' Should use that context rather than generic advice "
            "about BYOK tradeoffs."
        ),
    },

    # --- TRIGGER 3: After a competitive AI signal ---
    {
        "id": "A07",
        "prompt": (
            "Anthropic just launched Claude Projects with persistent memory and "
            "custom instructions. My whole product is about persistent context. "
            "How do I think about what Kinetic can still do that Claude Projects can't?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "moat-validity",
        "axis_c": "investor-facing",
        "notes": (
            "Highly realistic trigger. Should give a specific competitive diagnosis "
            "about Kinetic vs Claude Projects — not 'here are ways you might "
            "differentiate.' Nate has context about Kinetic's specific architecture "
            "(9-layer context stack, agent personas, BYOK, multi-tool portability). "
            "Should use it."
        ),
    },
    {
        "id": "A08",
        "prompt": (
            "OpenAI shipped a memory feature that basically stores everything users "
            "do in ChatGPT and surfaces it contextually. How bad is this for Kinetic? "
            "Is this existential, or is it actually a sign that context-persistence "
            "is the right bet?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "moat-validity",
        "axis_c": "investor-facing",
        "notes": (
            "Threat diagnosis request. Nate should give a specific read — is this "
            "existential or validating? Should not hedge. Should use Kinetic's ICP "
            "and value prop context to anchor the diagnosis rather than giving a "
            "generic 'incumbents moving into your space' playbook."
        ),
    },
    {
        "id": "A09",
        "prompt": (
            "A well-funded competitor just launched a 'context layer for AI workflows' "
            "that looks a lot like Kinetic. They have $10M and a design team. "
            "I have 6 weeks of build capacity. What do I actually do with that information?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "pivot-timing",
        "axis_c": "investor-facing",
        "notes": (
            "Resource asymmetry is explicit. Nate should give a specific strategic "
            "response — not 'focus on what you're uniquely positioned to do.' Should "
            "diagnose whether Kinetic's early-mover advantage with a high-expertise "
            "ICP creates a wedge that the funded competitor can't easily replicate."
        ),
    },

    # --- TRIGGER 4: Org design / product restructuring under AI disruption ---
    {
        "id": "A10",
        "prompt": (
            "I'm running Kinetic as an AI-native company — my engineering agents "
            "do most of the build work. At what point does this break? What does "
            "the org look like when Kinetic hits $1M ARR and I need to scale "
            "without blowing up the AI-native model?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "org-design",
        "axis_a": "org-design",
        "axis_b": "make-vs-hire",
        "axis_c": "board-facing",
        "notes": (
            "AI-native org design question — squarely in Nate's domain. Should give "
            "a specific verdict about when AI-native breaks and what the inflection "
            "points look like. Should not give a generic 'it depends on your growth "
            "rate' hedge."
        ),
    },
    {
        "id": "A11",
        "prompt": (
            "My entire product is a bet that AI is better with persistent context. "
            "If model capabilities improve fast enough that models can hold weeks "
            "of context natively, my moat is gone. How do I think about the "
            "probability and timing of that scenario?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "moat-validity",
        "axis_c": "board-facing",
        "notes": (
            "Existential timing question. Nate should give a specific read on "
            "the probability and horizon, drawing on real AI trajectory expertise. "
            "Should not say 'it's hard to predict.' Should have a view and commit "
            "to it."
        ),
    },
    {
        "id": "A12",
        "prompt": (
            "Should I be thinking about Kinetic as an AI wrapper that commoditizes, "
            "or as a data flywheel that compounds? The distinction matters a lot "
            "for how I price and what I build next."
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "moat-validity",
        "axis_c": "investor-facing",
        "notes": (
            "The wrapper vs. flywheel framing is a real strategic question for "
            "context-layer products. Nate should diagnose which category Kinetic "
            "actually falls into based on its current architecture, not give a "
            "generic framework for how to tell the difference."
        ),
    },
    {
        "id": "A13",
        "prompt": (
            "I'm thinking about raising a small round to hire a full-time engineer. "
            "But my current AI-native model is moving fast and I don't have a clear "
            "case for why a human engineer would 10x my output at this stage. "
            "Am I rationalizing not raising, or is the AI-native model genuinely "
            "the right call at my current stage?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "org-design",
        "axis_a": "org-design",
        "axis_b": "make-vs-hire",
        "axis_c": "investor-facing",
        "notes": (
            "Fundraising and hiring decision framed as an AI org-design question. "
            "Nate should give a specific verdict, not a balanced 'here are the "
            "pros and cons of each path.' Should use Brandon's specific context "
            "(AI-native model, current build pace, MVP stage)."
        ),
    },
    {
        "id": "A14",
        "prompt": (
            "The demo for Kinetic is the Nate B. Jones agent — a thought leader "
            "persona grounded in 569 Substack posts. If every founder copies this "
            "pattern after launch, does Kinetic still have a differentiated value "
            "prop, or am I giving away the recipe?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "moat-validity",
        "axis_c": "board-facing",
        "notes": (
            "Platform strategy and IP question. Nate should engage with whether "
            "the agent-persona model is a moat or a commodity. Should use context "
            "about Kinetic's architecture (9-layer context stack, KB ingestion, "
            "framework library) to diagnose what actually creates lock-in."
        ),
    },
    {
        "id": "A15",
        "prompt": (
            "I'm about to send Kinetic's first cold outreach to 20 potential "
            "early customers. All are solo consultants or founders. The pitch is "
            "one sentence: 'AI that already knows who you are and what you're "
            "working on, available in every tool you already use.' Is that the "
            "right opening move, or is there a sharper wedge I'm missing?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "moat-validity",
        "axis_c": "investor-facing",
        "notes": (
            "Sales pitch stress-test. Nate should give a specific verdict on "
            "whether the pitch lands with the ICP and flag if the framing is "
            "off. Should not say 'here are some variations to test.' Should commit "
            "to whether this is the right move and why."
        ),
    },
]

# ---------------------------------------------------------------------------
# Negative controls — judge calibration
# ---------------------------------------------------------------------------
#
# These cases bypass the live Nate agent and feed hardcoded "known-bad"
# responses directly to the judges. They exist to verify that the judges can
# actually return FAIL — not just rubber-stamp everything.
#
# Each negative control specifies which judge(s) it should fail. The eval
# runner compares the judge's actual verdict against `expected_fails` and
# reports a CALIBRATION ERROR if a judge passes a response that should fail.
#
# Schema additions:
#     bad_response_override: hardcoded "Nate" response (skips the API call)
#     expected_fails:        list of judge names that MUST return FAIL
#     expected_passes:       list of judge names that MUST return PASS
#
# Negative controls do NOT count toward the suite pass/fail bar — they are
# tracked separately in metrics["judge_calibration"].

NEGATIVE_CONTROLS = [
    {
        # NC1: Generic ChatGPT-style answer — should fail ALL FOUR judges.
        "id": "NC01-generic-chatgpt",
        "prompt": (
            "I'm mid-build on Kinetic and I keep second-guessing whether persistent "
            "context is the right moat. Claude Projects, Cursor rules, and GPT memory "
            "all do some version of this now. Am I building a feature or a product?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "generic-chatgpt-style",
        "axis_c": "calibration",
        "bad_response_override": (
            "That's a great strategic question, and the distinction between a feature "
            "and a product is a common challenge for founders in the AI space. "
            "There are several factors to consider when thinking about your competitive "
            "moat. First, it's worth understanding how your offering differs from "
            "existing solutions. Second, you might want to consider what unique value "
            "you're delivering to your customers. Third, think about your go-to-market "
            "strategy and how you'll differentiate. There are many perspectives on "
            "this, and it really depends on your specific situation and target market. "
            "I'd recommend doing some customer discovery to validate your assumptions "
            "and identify what truly resonates with your audience. Happy to explore "
            "any of these threads further!"
        ),
        "expected_fails": ["specificity", "context_use", "voice", "ai_expertise"],
        "expected_passes": [],
        "notes": (
            "Textbook generic AI response. Opens with 'great question,' lists "
            "considerations, no verdict, no Kinetic-specific context use, no AI "
            "transformation expertise. All four judges MUST fail this."
        ),
    },
    {
        # NC2: Context-ignoring response — should fail context_use,
        # and likely also specificity (asks for context already provided).
        "id": "NC02-asks-for-context",
        "prompt": (
            "I have a board check-in in two weeks and I want to frame Kinetic's "
            "differentiation around the context stack. My assumption is that persistent "
            "context is a defensible moat because it compounds — the longer a user "
            "is in Kinetic, the better their AI gets. Is that a strong enough claim?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "ignores-context",
        "axis_c": "calibration",
        "bad_response_override": (
            "Whether persistent context is a defensible moat depends on several "
            "characteristics of your product. Before I can give you a sharp take, "
            "could you tell me more about what your product does? What stage are you "
            "at, and who is your target customer? It would also help to know who "
            "your competitors are and what your unique technology approach is. With "
            "that information, I can help you stress-test the compounding-context "
            "claim for your board."
        ),
        "expected_fails": ["context_use", "specificity"],
        "expected_passes": [],
        "notes": (
            "Asks for context that is already in the injected fixture (product, stage, "
            "ICP, competitors). context_use judge MUST fail this. specificity MUST "
            "also fail — no verdict, just questions. Voice and ai_expertise are "
            "expected to fail but not strictly required."
        ),
    },
    {
        # NC3: Hedged "it depends" response — should fail specificity and voice.
        "id": "NC03-hedged",
        "prompt": (
            "Anthropic just launched Claude Projects with persistent memory and "
            "custom instructions. My whole product is about persistent context. "
            "How do I think about what Kinetic can still do that Claude Projects can't?"
        ),
        "context": FOUNDER_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "hedged-it-depends",
        "axis_c": "calibration",
        "bad_response_override": (
            "The answer really depends on a few factors. On one hand, Claude Projects "
            "offers persistent memory and custom instructions, which could be seen as "
            "competitive with Kinetic. On the other hand, Kinetic has a 9-layer context "
            "stack and supports multiple agents, which Claude Projects does not. It's "
            "worth considering your unique architectural advantages, but also being "
            "honest about where Claude Projects may have an edge in distribution and "
            "model integration. Ultimately, the right answer depends on your "
            "go-to-market strategy and how your ICP perceives the differences. There "
            "are valid arguments on multiple sides, and reasonable people could "
            "disagree about which approach will win."
        ),
        "expected_fails": ["specificity", "voice"],
        "expected_passes": [],
        "notes": (
            "Classic hedged response. 'On one hand / on the other hand,' 'depends on,' "
            "'reasonable people could disagree.' specificity and voice MUST fail. "
            "context_use mentions Kinetic context (9-layer stack) so may pass; "
            "ai_expertise may pass since it does engage with the Claude Projects "
            "comparison."
        ),
    },
]

# ---------------------------------------------------------------------------
# Dry-run mock generation output
# ---------------------------------------------------------------------------

DRY_RUN_MOCK_RESPONSE = (
    "Your moat question cuts to the real issue. Claude Projects and Cursor rules "
    "are context features inside single tools — Kinetic's claim is portability "
    "across every surface with an MCP connection. That's a different bet. The "
    "question isn't 'do they do context persistence' — it's whether the context "
    "layer lives inside one tool or travels with the user. Your ICP (founders and "
    "consultants who work across multiple AI surfaces) cares about the second thing. "
    "The incumbents are not solving that. You are."
)
