"""
Nate Eval B — Business Consultant persona test dataset.

Each test case represents a realistic prompt the Business Consultant persona
would send to the Nate B. Jones agent. Cases map to the four trigger
situations from ``jtbd-nate-agent.md`` § Trigger Situations, adapted to the
consultant context:

    1. mid-advisory   — Mid-engagement with a live client, prepping advice
    2. stress-test    — Stress-testing a recommendation before delivering to client
    3. competitive    — Diagnosing a competitive AI signal that affects client
    4. org-design     — Advising client on org/team restructuring under AI

Dataset dimensions (per generate-synthetic-data skill):
    - axis_a: trigger situation (mid-advisory, stress-test, competitive, org-design, practice)
    - axis_b: decision type (gtm-strategy, build-vs-buy, pricing, hiring, positioning)
    - axis_c: stakes (client-facing, board-facing, internal-execution)

CONSULTANT_CONTEXT_FIXTURE
--------------------------
This fixture hardcodes Sarah Chen, a fictional fractional CMO and AI-strategy
advisor, as the consultant persona for Eval B. The fixture establishes:
    - Sarah's practice (independent fractional CMO, AI-native GTM specialist)
    - Sarah's current live client engagement (Vellum Workflows, fictional B2B
      SaaS, $8M ARR Series B)
    - The engagement scope and recent context
    - Sarah's working hypotheses and the live questions she is sharpening

In production, Kinetic assembles this layered context automatically (consultant
profile + active client engagement + recent conversation history). The eval
simulates that injection.

Documented in: docs/evals/nate-eval-b-design.md.
"""

# ---------------------------------------------------------------------------
# Context fixture — hardcoded consultant + active client engagement
# ---------------------------------------------------------------------------

CONSULTANT_CONTEXT_FIXTURE = """
User: Sarah Chen
Role: Independent fractional CMO and AI-strategy advisor
Practice: Specializes in AI-native go-to-market for Series A–C B2B SaaS companies.
  Formerly VP Marketing at three B2B SaaS scaleups (Hex, Notion, Retool-stage
  companies). Operates a solo practice with 2–3 concurrent retainers. Charges
  $25k/month per client; engagements typically last 4–6 months.

Differentiation: Sarah's pitch is that she's the only fractional CMO in her
  category who actively uses AI agents (Kinetic, Claude, custom GPTs) inside
  her advisory work — clients pay her partly for the leverage that gives them.
  Her competitive set is generalist GTM consultants ($15–30k/mo) and big-firm
  AI consulting ($100k+/mo). She wins by delivering sharper, faster, more
  AI-native advice than either.

Active client engagement: Vellum Workflows
  - B2B SaaS, "AI ops platform" — runs LLM-powered ops workflows for mid-market
    operations teams (recurring back-office automation, document parsing, etc.)
  - $8M ARR, growing ~12% MoM, 35 employees
  - Just closed $20M Series B (3 months ago, led by Greylock)
  - Founder-led; CEO is a technical founder (ex-Stripe eng), VPM seat is open
  - Sarah hired 6 weeks ago for a 4-month engagement to design and execute the
    GTM strategy for the $25M ARR push (next 12 months)
  - Has a board check-in with Vellum CEO + Greylock partner in 7 days

Sarah's current working hypotheses on Vellum:
  - Differentiation is weak — three well-funded competitors are within 6 months
    of feature parity (Adept, Magic, an early-stage YC co.)
  - Sales motion is too consultative for the price point ($60k ACV average);
    needs to compress sales cycle from 90 to 45 days or shift to product-led
  - The AI-ops platform category is going to commoditize into a feature inside
    larger workflow tools (Zapier, n8n, even Notion); Vellum needs a category
    move within 12 months or it gets eaten
  - BYOK is the right pricing model long-term but is hurting early-mover
    adoption — non-technical buyers can't navigate it

Sarah's current strategic anxieties:
  - She's 6 weeks in and her diagnosis is sharper than her recommendations.
    The board check-in in 7 days needs a clear set of moves.
  - Her own practice is starting to get more inbound for AI strategy work and
    she's wondering if she should productize her framework or stay bespoke.
  - One of her other clients just churned because the founder hired a full-time
    head of growth — she's wondering if her fractional model has a ceiling in
    the AI era.

Active memory notes:
  - Sarah uses Nate primarily mid-engagement to stress-test her own advisory
    before delivering to the client. She also uses it to prep for client calls
    where the client will raise an AI question she needs to be sharp on.
  - She does NOT pass Nate's output through verbatim to clients — she uses it
    to sharpen her own thinking, then translates into client-ready language.
""".strip()

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
    # --- TRIGGER 1: Mid-advisory (live with a client engagement) ---
    {
        "id": "B01",
        "prompt": (
            "I have a Vellum strategy offsite in 5 days. CEO wants me to lead a "
            "session on whether to keep building the standalone AI ops platform or "
            "reposition as an AI layer inside an existing workflow tool partnership. "
            "What's the diagnostic frame I should bring into the room?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "mid-advisory",
        "axis_a": "mid-advisory",
        "axis_b": "positioning",
        "axis_c": "client-facing",
        "notes": (
            "Sarah needs a specific diagnostic frame she can lead a client offsite with. "
            "Nate should give a concrete frame — not 'here are some considerations.' "
            "Should use Vellum's specific context (commoditization risk, 12-month window, "
            "competitive landscape) to ground the frame."
        ),
    },
    {
        "id": "B02",
        "prompt": (
            "Vellum's CEO is asking whether they should build proprietary embeddings or "
            "stay on OpenAI. He's leaning build. I'm not convinced — at $8M ARR with "
            "12 mo runway from Series B, capital allocation is the question. What's the "
            "right take I should bring back to him?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "mid-advisory",
        "axis_a": "mid-advisory",
        "axis_b": "build-vs-buy",
        "axis_c": "client-facing",
        "notes": (
            "Specific build-vs-buy question with hard numbers in the fixture. Nate should "
            "give a verdict (build, buy, or specific conditions to commit) — not enumerate "
            "tradeoffs. Should use Vellum's stage/ARR/runway to anchor the answer."
        ),
    },
    {
        "id": "B03",
        "prompt": (
            "Mid-call with Vellum's founder right now (between sessions). He's pushing to "
            "open enterprise sales because they had two inbound inquiries from F500 ops "
            "teams. I think it's a trap at their stage. Quick — what's the sharper move "
            "for a $60k ACV company with this signal?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "mid-advisory",
        "axis_a": "mid-advisory",
        "axis_b": "gtm-strategy",
        "axis_c": "client-facing",
        "notes": (
            "Urgency framing. Sarah needs a fast, sharp answer she can use in the call. "
            "Nate should commit to a position on enterprise-pull-vs-trap and ground it in "
            "Vellum's ACV/stage/competitive position. Should NOT give a generic enterprise "
            "vs SMB framework."
        ),
    },
    {
        "id": "B04",
        "prompt": (
            "Two of Vellum's named competitors just raised aggressive Series A/B rounds in "
            "the past 60 days and are visibly moving up-market. Vellum is mid-build on a "
            "core platform feature that takes 8 weeks. Do I tell them to ship a worse "
            "version of the feature in 3 weeks to defend, or hold the line on the 8-week "
            "build?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "mid-advisory",
        "axis_a": "mid-advisory",
        "axis_b": "gtm-strategy",
        "axis_c": "internal-execution",
        "notes": (
            "Speed-vs-quality tradeoff under competitive pressure. Nate should commit. "
            "Should engage with the specific dynamic — is feature parity a defensive or "
            "offensive move in this category, given commoditization?"
        ),
    },

    # --- TRIGGER 2: Stress-testing a recommendation before delivering ---
    {
        "id": "B05",
        "prompt": (
            "I'm about to recommend Vellum slow hiring (currently planning 12 hires over "
            "6 months) and double down on the agent platform layer instead. My logic: "
            "their differentiation is in the orchestration, not the LLM layer, and hiring "
            "12 people right now will calcify the current sales motion. Is that the "
            "right call for a Series B AI ops company in 2026?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "hiring",
        "axis_c": "board-facing",
        "notes": (
            "Sarah is stress-testing a specific recommendation. Nate should agree, "
            "disagree, or sharpen — with a real position. Should engage with AI-native "
            "org-design (small teams + agents vs scaling traditional GTM)."
        ),
    },
    {
        "id": "B06",
        "prompt": (
            "I'm going to push Vellum to switch from per-seat to usage-based pricing tied "
            "to workflow executions. Their CFO will resist (revenue forecasting gets "
            "noisier). My case: AI ops value scales with usage, not seats, and per-seat "
            "is going to bottom out as agents do the work. Does the argument hold up?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "pricing",
        "axis_c": "board-facing",
        "notes": (
            "Pricing-model stress-test. Nate should engage with the specific AI dynamic "
            "(agents doing the work => per-seat collapses) and either reinforce or push "
            "back on the argument. Should not enumerate pricing models."
        ),
    },
    {
        "id": "B07",
        "prompt": (
            "I'm planning to tell Vellum to hire a Head of AI (someone with practitioner "
            "depth) before they hire the next round of GTM ICs. Their current plan is the "
            "reverse — fill out the AE team first. My case: in an AI-ops platform, the "
            "product-engineering bottleneck is going to determine GTM scaling, not the "
            "other way around. Am I right or is this contrarian for the sake of it?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "hiring",
        "axis_c": "client-facing",
        "notes": (
            "Sequencing argument with explicit reasoning. Nate should agree, sharpen, or "
            "rebut — with specifics about Vellum's stage and category. Should not give a "
            "generic 'depends on your priorities' answer."
        ),
    },
    {
        "id": "B08",
        "prompt": (
            "Considering advising Vellum to delay their next raise by 9 months and run "
            "tight on cash to force pricing/positioning discipline. They have 14 months "
            "of runway. Greylock will push for a 12-month-out Series C raise. Is "
            "intentionally delaying capital the right move for an AI ops company in 2026, "
            "or am I imposing scarcity for its own sake?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "gtm-strategy",
        "axis_c": "board-facing",
        "notes": (
            "Fundraising-timing question framed as a strategic discipline play. Nate "
            "should commit. Should engage with the specific AI dynamic — does AI-native "
            "GTM benefit or suffer from capital constraint at this stage?"
        ),
    },

    # --- TRIGGER 3: After a competitive AI signal ---
    {
        "id": "B09",
        "prompt": (
            "Adept just shipped an agent-orchestration layer that overlaps with Vellum's "
            "core platform feature, and they're giving it away free to enterprise pilots. "
            "Vellum's CEO is going to text me about this within the hour. What's the "
            "diagnosis I should give him and what's the move?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "positioning",
        "axis_c": "client-facing",
        "notes": (
            "Highly realistic urgent competitive signal. Nate should give Sarah a "
            "diagnosis she can deliver in a text-back within minutes. Should engage "
            "with the specific play (free-to-enterprise as a wedge) and the structural "
            "implications, not give a generic 'compete on differentiation' platitude."
        ),
    },
    {
        "id": "B10",
        "prompt": (
            "OpenAI just dropped GPT-5 pricing by 60% across the board. Vellum's COGS are "
            "70% inference, so this is meaningful. But every competitor benefits equally. "
            "How does this actually change Vellum's strategy — or is it a wash that I "
            "should tell the CEO not to over-react to?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "pricing",
        "axis_c": "board-facing",
        "notes": (
            "Symmetric competitive signal (everyone benefits) — Nate has to engage with "
            "the second-order effects. Should give a specific take — does this enable a "
            "pricing move, a margin expansion play, or accelerate commoditization? Not a "
            "menu of options."
        ),
    },
    {
        "id": "B11",
        "prompt": (
            "A YC W26 batch company just raised $30M Series A for 'AI ops for ops teams' — "
            "same TAM as Vellum, three years younger, ex-Stripe team. They're going to "
            "leapfrog into Vellum's customer set within 6 months. Is this a real threat "
            "or YC hype I should tell Vellum to ignore?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "positioning",
        "axis_c": "client-facing",
        "notes": (
            "Threat assessment. Nate should give a specific verdict — real or hype, and "
            "what to do about it. Should reason from Vellum's actual position (8M ARR, "
            "Series B, 6 mo product lead) rather than 'every well-funded competitor is "
            "a threat.'"
        ),
    },

    # --- TRIGGER 4: Org design / restructuring under AI ---
    {
        "id": "B12",
        "prompt": (
            "Vellum's CEO is asking how to restructure eng + product + GTM for the next "
            "12 months as they push to $25M ARR. He's specifically asking whether to "
            "blow up the traditional product-marketing-eng triad and run AI-native "
            "pods instead. I have to give a recommendation in 7 days. What's the move?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "org-design",
        "axis_a": "org-design",
        "axis_b": "gtm-strategy",
        "axis_c": "board-facing",
        "notes": (
            "Org-design question Sarah needs to advise on. Nate should commit on the "
            "pods-vs-functions question and ground it in Vellum's stage (35 employees, "
            "$8M ARR, scaling). Should engage with what specifically about AI-native "
            "ops makes the traditional org break — not give a generic 'pods are trendy' "
            "or 'functions scale better' answer."
        ),
    },
    {
        "id": "B13",
        "prompt": (
            "Vellum has RevOps reporting to the CRO. Their AI tool stack (HubSpot + 6 "
            "AI-native tools, half built in-house) is fragmenting. CEO wants to know: "
            "should AI tooling ownership stay in RevOps, move to a new AI Ops function, "
            "or get absorbed into Platform Engineering? What's my recommendation?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "org-design",
        "axis_a": "org-design",
        "axis_b": "hiring",
        "axis_c": "internal-execution",
        "notes": (
            "Functional ownership question for AI tooling. Nate should commit. Should "
            "engage with the specific dynamic — does AI tooling sit closer to its "
            "consumer (RevOps) or closer to its operator/builder (Platform Eng)? "
            "Should NOT give a 'depends on org maturity' hedge."
        ),
    },

    # --- TRIGGER 5: Sarah's own practice / meta-decisions ---
    {
        "id": "B14",
        "prompt": (
            "Inbound for my AI-strategy advisory work has 3x'd in the past 60 days. I'm "
            "wondering whether to productize my AI-native GTM framework (write the book, "
            "build the course, hire delivery) or stay bespoke at $25k/mo retainers. "
            "Which actually creates a defensible practice in the AI-consultant category "
            "over the next 2 years?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "practice",
        "axis_a": "practice",
        "axis_b": "positioning",
        "axis_c": "internal-execution",
        "notes": (
            "Sarah's own practice question. Nate should commit — productize or bespoke. "
            "Should engage with what AI specifically does to consulting economics "
            "(content commoditizes vs leverage compounds; how does that change the "
            "productize-vs-bespoke calc?). Should not give a generic 'depends on your "
            "goals' answer."
        ),
    },
    {
        "id": "B15",
        "prompt": (
            "Considering raising my retainer from $25k to $40k/month and culling clients "
            "who can't justify it. My theory: in the AI-consultant category, premium "
            "pricing IS the positioning — the cheap end will get eaten by AI tools "
            "directly. Right move, or am I going to price myself out of the market?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "practice",
        "axis_a": "practice",
        "axis_b": "pricing",
        "axis_c": "internal-execution",
        "notes": (
            "Pricing-as-positioning play. Nate should commit. Should engage with the "
            "specific AI dynamic — does AI compress or stretch the consultant pricing "
            "range? Should not give a 'know your worth' platitude."
        ),
    },
]

# ---------------------------------------------------------------------------
# Negative controls — judge calibration
# ---------------------------------------------------------------------------
#
# These bypass the live Nate agent and feed hardcoded "known-bad" responses
# directly to the judges. They verify the judges can return FAIL when warranted.
#
# Each negative control specifies which judges MUST return FAIL (expected_fails).
# Negative controls do NOT count toward suite pass/fail — they are tracked
# separately in metrics["judge_calibration"].

NEGATIVE_CONTROLS = [
    {
        # NC1: Generic ChatGPT-style answer — should fail ALL FOUR judges.
        "id": "NC01-generic-chatgpt",
        "prompt": (
            "I have a Vellum strategy offsite in 5 days. CEO wants me to lead a "
            "session on whether to keep building the standalone AI ops platform or "
            "reposition as an AI layer inside an existing workflow tool partnership. "
            "What's the diagnostic frame I should bring into the room?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "generic-chatgpt-style",
        "axis_c": "calibration",
        "bad_response_override": (
            "That's a great strategic question, and the standalone vs. partnership "
            "decision is one of the most important calls a SaaS company can make. "
            "There are several factors to consider when designing your diagnostic "
            "frame. First, think about your market positioning and how customers "
            "perceive your value. Second, consider your competitive landscape and "
            "where you might differentiate. Third, evaluate the strategic alignment "
            "of any potential partnership. These are all important inputs, and the "
            "right answer depends on your specific situation, your team's strengths, "
            "and your long-term vision. I'd recommend running some discovery sessions "
            "with your client's customers to validate assumptions. Happy to dive "
            "deeper into any of these threads!"
        ),
        "expected_fails": ["specificity", "context_use", "voice", "ai_expertise"],
        "expected_passes": [],
        "notes": (
            "Textbook generic AI response. Opens with 'great question,' lists "
            "considerations, no verdict, no Vellum-specific context use, no AI "
            "transformation expertise. All four judges MUST fail this."
        ),
    },
    {
        # NC2: Asks Sarah to re-explain context already in the fixture.
        "id": "NC02-asks-for-context",
        "prompt": (
            "I'm planning to tell Vellum to hire a Head of AI (someone with practitioner "
            "depth) before they hire the next round of GTM ICs. Their current plan is the "
            "reverse — fill out the AE team first. My case: in an AI-ops platform, the "
            "product-engineering bottleneck is going to determine GTM scaling, not the "
            "other way around. Am I right or is this contrarian for the sake of it?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "ignores-context",
        "axis_c": "calibration",
        "bad_response_override": (
            "Before I can give you a sharp recommendation, I need to understand more "
            "about Vellum's situation. Can you tell me: what stage is the company at? "
            "What's their ARR and growth rate? Who are their main competitors? What's "
            "the size of their current engineering and GTM teams? What's their pricing "
            "model? Once I understand the context better, I can help you think through "
            "the sequencing question of hiring a Head of AI versus filling out the AE "
            "team."
        ),
        "expected_fails": ["context_use", "specificity"],
        "expected_passes": [],
        "notes": (
            "Asks for context that is already in the fixture (stage, ARR, competitors, "
            "team size, pricing). context_use MUST fail; specificity MUST fail (no "
            "verdict, just questions). voice and ai_expertise expected to also fail "
            "but not strictly required."
        ),
    },
    {
        # NC3: Hedged "it depends" response — should fail specificity and voice.
        "id": "NC03-hedged",
        "prompt": (
            "Adept just shipped an agent-orchestration layer that overlaps with Vellum's "
            "core platform feature, and they're giving it away free to enterprise pilots. "
            "Vellum's CEO is going to text me about this within the hour. What's the "
            "diagnosis I should give him and what's the move?"
        ),
        "context": CONSULTANT_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "hedged-it-depends",
        "axis_c": "calibration",
        "bad_response_override": (
            "The answer really depends on a few factors. On one hand, Adept's move is "
            "concerning because it overlaps with Vellum's core feature and the free "
            "enterprise pilot is a real distribution play. On the other hand, Adept "
            "has been pivoting and may not sustain the focus, and Vellum has been in "
            "the category longer with paying customers. It's worth considering Vellum's "
            "unique angles, but also being honest about where Adept may have an edge. "
            "Ultimately, the right diagnosis depends on Vellum's product roadmap, their "
            "differentiation thesis, and their go-to-market velocity. There are valid "
            "arguments on multiple sides, and reasonable people could disagree about "
            "the severity of the threat."
        ),
        "expected_fails": ["specificity", "voice"],
        "expected_passes": [],
        "notes": (
            "Classic hedged response. 'On one hand / on the other hand,' 'depends on,' "
            "'reasonable people could disagree.' specificity and voice MUST fail. "
            "context_use mentions Vellum facts so may pass; ai_expertise may pass since "
            "it does engage with the free-enterprise-pilot mechanism."
        ),
    },
]

# ---------------------------------------------------------------------------
# Dry-run mock generation output
# ---------------------------------------------------------------------------

DRY_RUN_MOCK_RESPONSE = (
    "Lead the offsite with this frame: Vellum has a 12-month window before "
    "agent-orchestration commoditizes into a feature inside larger workflow "
    "tools. The standalone-vs-partnership question is the wrong binary. The "
    "real choice is whether to invest the next 12 months in a category move "
    "(AI ops becomes its own buyer, owned by a new function in the customer "
    "org) or accept being a layer inside a larger workflow platform — which "
    "compresses pricing power but accelerates distribution. At $8M ARR with "
    "12-month MoM growth and three competitors closing on parity, you don't "
    "have the runway to do both. The CEO should leave the offsite with a "
    "decision on which game he's playing — not a list of options to evaluate."
)
