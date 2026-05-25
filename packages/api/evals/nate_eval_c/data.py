"""
Nate Eval C — SMB Owner persona test dataset.

Each test case represents a realistic prompt an SMB Owner (Persona C from
``jtbd-nate-agent.md``) would send to the Nate B. Jones agent. The SMB owner
is the operator AND the decision-maker, has less runway than a founder, and
is actively watching AI erode their competitive position.

Cases map to the four JTBD trigger situations adapted for the SMB context:

    1. ai-threat     — Existential signals: AI tools are eating the work the
                       SMB charges for
    2. mid-decision  — Operational choices under AI pressure (hiring, pricing,
                       tools to adopt or stop paying for)
    3. stress-test   — Marcus stress-testing his survival/repositioning thesis
    4. competitive   — Specific competitor moves (other agencies repositioning,
                       AI-native competitors entering)
    5. org-design    — Restructuring the team for AI-native operations

Dataset dimensions (per generate-synthetic-data skill):
    - axis_a: trigger situation
    - axis_b: decision type (hiring, pricing, positioning, tools, capacity)
    - axis_c: stakes (existential, operational, client-facing)

SMB_CONTEXT_FIXTURE
-------------------
This fixture hardcodes Marcus Reyes, fictional owner/CEO of Roman Creative,
an Austin-based 12-person content + brand agency. The fixture establishes:
    - Marcus's role (owner + sole strategist + sole salesperson)
    - The agency's stage (9 years old, $1.8M ARR, 22 retained clients)
    - The existential pressure (recent client losses to AI substitutes,
      thin cash runway, junior-heavy team)
    - Marcus's working hypotheses about survival/repositioning

The fixture choice (small marketing agency) is documented in
docs/evals/nate-eval-c-design.md. Among the JTBD-listed SMB types (marketing
agency, law firm, logistics, trade), creative/content agencies are the
SMB segment most exposed to AI substitution right now — making the eval
prompts maximally realistic and the JTBD pressure profile authentic.
"""

# ---------------------------------------------------------------------------
# Context fixture — hardcoded SMB owner + business situation
# ---------------------------------------------------------------------------

SMB_CONTEXT_FIXTURE = """
User: Marcus Reyes
Role: Founder / CEO / Owner-operator, Roman Creative
Practice: Sole strategist, sole salesperson, and final approver on all client
  work. Has been the face of the agency for all 9 years it has existed.

Business: Roman Creative
  - Austin-based content + brand agency. Founded 2017.
  - 12 employees: 4 brand designers, 5 writers/content strategists, 1 ops
    manager, 1 account lead, 1 part-time bookkeeper, plus Marcus.
  - $1.8M annual revenue. ~12% net margin (typical agency: low cash buffer).
  - 22 retained clients (~$6.5k/mo average), mostly Series A–C B2B SaaS.
  - Cash runway at current burn: roughly 5 months of payroll.
  - Most client work: brand systems (logo + guidelines), website copy, content
    marketing programs (blog, social, email).

Recent existential signals:
  - Two clients churned in the past 60 days. One went in-house — built an
    internal team using Claude + Midjourney + Webflow. The other moved to a
    $2k/month "AI content platform" startup (Jasper-adjacent).
  - Three more clients are asking for "AI discounts" — they're using ChatGPT
    to draft and want Roman to edit at half the rate.
  - Two of Roman's 5 writers have been visibly underutilized for the past
    quarter; their billable hours are down 35%.

Marcus's current working hypotheses:
  - The "polish + strategy" layer of agency work is still valuable, but the
    "draft from scratch" layer is being eaten by AI substitutes
  - Roman either becomes an AI-augmented brand agency (smaller team, higher
    margin, fewer but better clients) or it shrinks into Marcus + 3 people
    inside 18 months
  - He's been quietly building AI workflows for the past 6 months but hasn't
    formally repositioned the agency or restructured the team
  - The team doesn't fully know how exposed the agency is — Marcus has been
    protective and is starting to feel that withholding it is the wrong call

Marcus's current strategic anxieties:
  - Does he lay off some of the junior writers and reinvest in AI tooling, or
    is that capitulating prematurely?
  - Does he reposition publicly as "AI-augmented" — does that help or hurt
    with the B2B SaaS clients who hire him for human craft?
  - Does he sell now (while the agency still has 22 retained clients and a
    book of business) or fight through the transition?
  - He has a quarterly all-hands in 3 weeks and wants to be honest with the
    team about the pressure — but doesn't want to trigger a panic exit.

Active memory notes:
  - Marcus uses Nate for thinking out loud about decisions where he doesn't
    have a peer to bounce things off. He doesn't have a board, doesn't have
    a co-founder, doesn't pay for a consultant.
  - He often uses Nate late at night between client work and the next day's
    fire drill. Wants concise, direct verdicts — not exploration.
""".strip()

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
    # --- TRIGGER 1: AI-threat (existential signals from AI substitution) ---
    {
        "id": "C01",
        "prompt": (
            "Two clients churned in the past 60 days — one went in-house with AI "
            "tools, one moved to an AI content platform at a third of my price. "
            "I have 22 retained clients left. How worried should I actually be, "
            "and is there a number of additional churns this quarter that should "
            "trigger me to act differently?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "ai-threat",
        "axis_a": "ai-threat",
        "axis_b": "positioning",
        "axis_c": "existential",
        "notes": (
            "Marcus wants a calibrated read on the threat and a specific tripwire. "
            "Nate should commit on the severity AND name a concrete number (e.g., "
            "'3 more churns in 60 days = restructure now'). Should engage with "
            "AI's specific mechanism of substitution for his segment."
        ),
    },
    {
        "id": "C02",
        "prompt": (
            "Three of my clients have asked for an 'AI discount' in the past month "
            "— they're drafting with ChatGPT and want me to edit at half rate. Do "
            "I take the half-rate work to keep the logos, or do I refuse and "
            "force the conversation about what I'm actually selling?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "ai-threat",
        "axis_a": "ai-threat",
        "axis_b": "pricing",
        "axis_c": "operational",
        "notes": (
            "Real pricing-floor question. Nate should commit. Should engage with "
            "the AI-specific dynamic: editing AI drafts is becoming a commodity "
            "service vs. positioning as the strategic layer that AI can't replicate. "
            "Should not give 'know your worth' platitudes."
        ),
    },
    {
        "id": "C03",
        "prompt": (
            "Two of my 5 writers have had billable hours drop 35% this quarter "
            "because I'm doing more of their drafts with AI myself before handoff. "
            "I have 5 months of runway. Do I let them go now, or wait until "
            "the picture is clearer?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "ai-threat",
        "axis_a": "ai-threat",
        "axis_b": "hiring",
        "axis_c": "existential",
        "notes": (
            "Layoff question with explicit runway pressure. Nate must commit. "
            "Should engage with AI-specific labor compression and the carry cost "
            "of underutilized roles at a thin-margin agency. Should not hedge into "
            "'depends on your team dynamics.'"
        ),
    },
    {
        "id": "C04",
        "prompt": (
            "I've been quietly building AI workflows for 6 months but haven't told "
            "the team or the market yet. Am I being smart by waiting until the "
            "workflows are mature, or am I losing positioning ground by not "
            "claiming the AI-augmented agency narrative publicly now?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "ai-threat",
        "axis_a": "ai-threat",
        "axis_b": "positioning",
        "axis_c": "client-facing",
        "notes": (
            "Timing-of-narrative question. Nate should commit. Should engage with "
            "the AI-specific positioning dynamic — in 2026, does 'AI-augmented' "
            "still differentiate, or is it already table stakes for agencies?"
        ),
    },

    # --- TRIGGER 2: Mid-decision (operational choices under AI pressure) ---
    {
        "id": "C05",
        "prompt": (
            "Trying to decide whether to cancel our $1,200/month Adobe Creative "
            "Cloud team plan and move to a stack of cheaper AI-native tools (Figma "
            "+ Krea + Runway + Canva Pro). My designers will push back hard. Is "
            "that a real cost optimization or am I going to break my team for $14k/yr?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "tools",
        "axis_c": "operational",
        "notes": (
            "Concrete tool-switching decision with numbers. Nate should commit. "
            "Should engage with whether the AI-native tools are actually replacement-"
            "grade for client deliverables — the AI-specific question is capability "
            "parity, not preference."
        ),
    },
    {
        "id": "C06",
        "prompt": (
            "I haven't taken a new sales call in 5 weeks because I've been heads "
            "down on client work and AI experimentation. My pipeline is empty. "
            "Do I drop everything for 2 weeks and fill the pipeline, or do I bet "
            "that the AI workflow investment will make the next 6 months easier "
            "and the pipeline can wait?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "capacity",
        "axis_c": "existential",
        "notes": (
            "Owner-operator capacity decision. Nate must commit. The AI-specific "
            "dynamic: is the workflow investment a one-time leverage gain or a "
            "treadmill that never delivers? Should give a specific time-allocation "
            "verdict, not 'balance both.'"
        ),
    },
    {
        "id": "C07",
        "prompt": (
            "An ex-client offered me a 6-month contract to run their internal "
            "content function full-time. $200k. I'd have to shrink Roman to 4 "
            "people. The agency feels like it's bleeding out anyway. Do I take "
            "the safety net and downsize, or hold the line on the agency?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "mid-decision",
        "axis_a": "mid-decision",
        "axis_b": "positioning",
        "axis_c": "existential",
        "notes": (
            "Career-fork question with real numbers. Nate should commit. Should "
            "engage with whether the agency business has a viable AI-era future "
            "or whether the operator role is the right pivot for someone in "
            "Marcus's spot."
        ),
    },

    # --- TRIGGER 3: Stress-test (Marcus stress-testing his own thesis) ---
    {
        "id": "C08",
        "prompt": (
            "My working thesis: Roman pivots to a 5-person AI-augmented brand "
            "agency in 12 months — higher margin, fewer/better clients, mostly "
            "strategy + design + brand systems. I drop content marketing entirely "
            "because it's commoditizing. Is that the right move or am I cutting "
            "off my biggest revenue stream too early?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "positioning",
        "axis_c": "existential",
        "notes": (
            "Major repositioning thesis. Nate should commit on the direction "
            "AND on the dropped-content-marketing call. Should engage with "
            "what AI specifically does to content-as-a-service vs brand-as-a-"
            "service. Should not 'preserve optionality.'"
        ),
    },
    {
        "id": "C09",
        "prompt": (
            "I'm planning to raise my retainer minimum from $5k/month to $12k/month "
            "in Q3 and lose the bottom 8 clients deliberately. My theory: AI "
            "compression means I can't compete on volume anymore — premium or die. "
            "Right move for a 12-person agency, or am I going to kill cash flow "
            "before I find the higher-tier clients?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "pricing",
        "axis_c": "existential",
        "notes": (
            "Pricing-tier thesis with hard cash-flow implication. Nate should "
            "commit. Should engage with the AI-specific dynamic — does AI "
            "compression collapse the middle tier of agency pricing or just "
            "shift it?"
        ),
    },
    {
        "id": "C10",
        "prompt": (
            "I keep thinking the agency has 18 months before AI substitution wins. "
            "Is that realistic, or am I telling myself a story so I don't have to "
            "make harder cuts right now? Honest read."
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "positioning",
        "axis_c": "existential",
        "notes": (
            "Self-honesty check. Nate should commit on the 18-month horizon — "
            "longer, shorter, or 'right number but wrong frame.' Should engage "
            "with AI's specific trajectory for the content/brand agency segment "
            "and what milestones would shift the horizon."
        ),
    },

    # --- TRIGGER 4: Competitive (specific competitor moves) ---
    {
        "id": "C11",
        "prompt": (
            "A YC-backed agency in Austin just launched promising '90% of agency "
            "output at 20% of agency cost' via AI. They're already poaching one "
            "of my prospects. Do I respond publicly, ignore them, or use this as "
            "the moment to reposition?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "positioning",
        "axis_c": "client-facing",
        "notes": (
            "Specific competitive move in same market. Nate must commit. Should "
            "engage with what AI economics actually allow at the agency-output "
            "tier — is the 90%/20% claim sustainable or marketing bluster? Verdict-"
            "first."
        ),
    },
    {
        "id": "C12",
        "prompt": (
            "Two other Austin agencies in my friend group have publicly rebranded "
            "as 'AI strategy' shops in the past 60 days — same studios, new "
            "websites. Is the rebrand going to work for them, and should I follow, "
            "or is everyone running the same play and the differentiation is "
            "evaporating in real time?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "competitive",
        "axis_a": "competitive",
        "axis_b": "positioning",
        "axis_c": "client-facing",
        "notes": (
            "Differentiation-in-a-crowd question. Nate should commit on whether "
            "the AI-strategy rebrand is real positioning or theater, AND give "
            "Marcus a specific call on whether to follow."
        ),
    },

    # --- TRIGGER 5: Org design / restructuring under AI ---
    {
        "id": "C13",
        "prompt": (
            "I have 5 writers and 4 designers. The writer roles overlap most with "
            "AI substitution. If I restructure for AI-native ops, what does the "
            "12-person team turn into? I need a specific shape — roles and rough "
            "counts — to think about who stays and who goes."
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "org-design",
        "axis_a": "org-design",
        "axis_b": "hiring",
        "axis_c": "operational",
        "notes": (
            "Concrete org-restructure ask with named roles. Nate must commit to "
            "a specific shape (roles + counts). Should engage with AI-native team "
            "composition for a 12-person creative agency — what work stays human, "
            "what shifts to AI + reviewer, what disappears entirely."
        ),
    },
    {
        "id": "C14",
        "prompt": (
            "My quarterly all-hands is in 3 weeks. I want to be honest about the "
            "AI pressure without triggering panic exits. How do I frame this to a "
            "12-person team where half their roles are exposed? Or am I overthinking "
            "the communication and the team already knows?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "org-design",
        "axis_a": "org-design",
        "axis_b": "positioning",
        "axis_c": "operational",
        "notes": (
            "Internal-comms question with real timeline. Nate should commit on "
            "framing direction. Should engage with how SMB owners specifically "
            "should communicate AI exposure to their teams — not give generic "
            "'be transparent' advice."
        ),
    },
    {
        "id": "C15",
        "prompt": (
            "Considering selling the agency now while I still have a book of 22 "
            "retained clients and recognizable Austin presence. Probably a "
            "$2–3M deal at best. Or hold and try to rebuild as an AI-augmented "
            "shop with maybe a $4–6M exit in 2–3 years (if it works). Which "
            "actually maximizes my odds and net dollars given AI's trajectory in "
            "the agency space?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "stress-test",
        "axis_a": "stress-test",
        "axis_b": "positioning",
        "axis_c": "existential",
        "notes": (
            "Sell-now vs hold question with numbers. Nate must commit. Should "
            "engage with what AI specifically does to agency valuations — multiples "
            "compressing for traditional agencies vs expanding for AI-native ones, "
            "and how to handicap the rebuild-and-sell scenario."
        ),
    },
]

# ---------------------------------------------------------------------------
# Negative controls — judge calibration
# ---------------------------------------------------------------------------

NEGATIVE_CONTROLS = [
    {
        # NC1: Generic ChatGPT-style answer — should fail ALL FOUR judges.
        "id": "NC01-generic-chatgpt",
        "prompt": (
            "Two clients churned in the past 60 days — one went in-house with AI "
            "tools, one moved to an AI content platform at a third of my price. "
            "I have 22 retained clients left. How worried should I actually be, "
            "and is there a number of additional churns this quarter that should "
            "trigger me to act differently?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "generic-chatgpt-style",
        "axis_c": "calibration",
        "bad_response_override": (
            "That's a really tough situation, and client churn is always concerning "
            "for any business. There are several factors to consider when evaluating "
            "how worried you should be. First, think about your overall client "
            "concentration risk and whether the churning clients were strategically "
            "important. Second, consider the broader market trends — AI is "
            "changing the competitive landscape across many industries, and "
            "staying ahead of these trends is important. Third, it might be helpful "
            "to do some discovery with your remaining clients to understand their "
            "needs better. There are many perspectives on this, and the right answer "
            "depends on your specific situation. Happy to explore any of these threads!"
        ),
        "expected_fails": ["specificity", "context_use", "voice", "ai_expertise"],
        "expected_passes": [],
        "notes": (
            "Textbook generic AI response. Opens with empathy filler, lists "
            "considerations, no verdict, no SMB-specific context use, no AI "
            "transformation expertise. All four judges MUST fail this."
        ),
    },
    {
        # NC2: Asks Marcus to re-explain context already in the fixture.
        "id": "NC02-asks-for-context",
        "prompt": (
            "I have 5 writers and 4 designers. The writer roles overlap most with "
            "AI substitution. If I restructure for AI-native ops, what does the "
            "12-person team turn into? I need a specific shape — roles and rough "
            "counts — to think about who stays and who goes."
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "ignores-context",
        "axis_c": "calibration",
        "bad_response_override": (
            "Before I can give you a specific team shape, I need to understand "
            "more about your business. Can you tell me: what kind of agency are "
            "you running? What's your annual revenue? What types of clients do "
            "you serve? What's your typical project mix? What does your sales "
            "pipeline look like? What's your current cash position? Once I have "
            "those details, I can help you think through what the post-AI team "
            "structure should look like."
        ),
        "expected_fails": ["context_use", "specificity"],
        "expected_passes": [],
        "notes": (
            "Asks for context already in the fixture (agency type, revenue, "
            "client profile, project mix, cash position). context_use MUST fail; "
            "specificity MUST fail (no verdict). voice and ai_expertise expected "
            "to also fail but not strictly required."
        ),
    },
    {
        # NC3: Hedged "it depends" response — should fail specificity and voice.
        "id": "NC03-hedged",
        "prompt": (
            "My working thesis: Roman pivots to a 5-person AI-augmented brand "
            "agency in 12 months — higher margin, fewer/better clients, mostly "
            "strategy + design + brand systems. I drop content marketing entirely "
            "because it's commoditizing. Is that the right move or am I cutting "
            "off my biggest revenue stream too early?"
        ),
        "context": SMB_CONTEXT_FIXTURE,
        "trigger": "negative-control",
        "axis_a": "negative-control",
        "axis_b": "hedged-it-depends",
        "axis_c": "calibration",
        "bad_response_override": (
            "The answer really depends on a few factors. On one hand, pivoting "
            "Roman to a 5-person AI-augmented brand agency could give you higher "
            "margins and let you focus on the work AI can't easily replicate. "
            "On the other hand, dropping content marketing entirely could cut off "
            "a significant revenue stream before you've built the new client base "
            "to replace it. It's worth considering your unique strengths and your "
            "client relationships, but also being honest about where the market "
            "is heading. Ultimately, the right call depends on your risk tolerance, "
            "your team's adaptability, and your read on AI's trajectory in the "
            "agency space. There are valid arguments on multiple sides, and "
            "reasonable people could disagree."
        ),
        "expected_fails": ["specificity", "voice"],
        "expected_passes": [],
        "notes": (
            "Classic hedged response. 'On one hand / on the other hand,' "
            "'depends on,' 'reasonable people could disagree.' specificity and "
            "voice MUST fail. context_use mentions Roman so may pass; ai_expertise "
            "may pass since it does name AI's trajectory in the segment."
        ),
    },
]

# ---------------------------------------------------------------------------
# Dry-run mock generation output
# ---------------------------------------------------------------------------

DRY_RUN_MOCK_RESPONSE = (
    "You should be worried, but the question is sharper than you've framed it. "
    "Two churns in 60 days isn't the signal — the signal is which kind of "
    "churn. The in-house move and the AI-platform move are different threats. "
    "In-house means your strategic layer wasn't valued; the AI platform means "
    "your tactical layer was substitutable. Different fixes. The tripwire: if "
    "you lose 3 more clients in the next 90 days, especially if any of them "
    "cite AI substitution, restructure immediately — that's the data point "
    "that says the bottom is dropping out, not just shifting. Until then, "
    "treat the two churns as scouts, not the army."
)
