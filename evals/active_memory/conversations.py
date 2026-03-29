"""
Synthetic conversation fixtures for Active Memory proposal eval (KIN-328).

17 conversations covering: factual/decision-rich, opinion-based, task-focused,
no-memorable-facts, contradicting-statements, and very-short edge cases.

Each fixture is a list of {"role": "user"/"assistant", "content": "..."} messages —
matching the format fed to the BYOK LLM in _generate_proposals_job.
"""

# ---------------------------------------------------------------------------
# Scoring rubric reference
# ---------------------------------------------------------------------------
#
# Each proposal scored 0-2:
#   0 = wrong / irrelevant / hallucinated / verbatim quote
#   1 = acceptable — vaguely relevant but imprecise or redundant
#   2 = good — specific, durable, directly actionable for future collaboration
#
# Target: mean score ≥ 1.5 across ALL proposals from ALL conversations.
# Edge case targets: sparse/empty for no-facts conversations; latest-wins for contradictions.

CONVERSATIONS = [

    # ── Category A: Factual / decision-rich (8 conversations) ──────────────

    {
        "id": "conv-001",
        "label": "engineering-preferences",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "I want to discuss how I prefer to structure backend APIs."},
            {"role": "assistant", "content": "Sure — what's your current stack and preference?"},
            {"role": "user", "content": "I'm building in FastAPI with Python. I strongly prefer thin controllers — all business logic goes in services, not routes. Routes should just validate input and delegate."},
            {"role": "assistant", "content": "That maps well to a repository pattern. Do you use dependency injection for your services?"},
            {"role": "user", "content": "Yes, I use FastAPI's Depends() everywhere. I also refuse to put database calls directly in route handlers. It violates the principle too much."},
            {"role": "assistant", "content": "Agreed. Any other patterns you care about?"},
            {"role": "user", "content": "I never catch broad exceptions. I'd rather have a crash and a proper error log than silently swallowed failures. That's burned me too many times."},
        ],
        "must_capture": ["thin controllers / business logic in services", "refuses database calls in route handlers", "never catches broad exceptions"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-002",
        "label": "communication-style",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "I find bullet points really unhelpful in most AI responses. I prefer structured prose."},
            {"role": "assistant", "content": "Noted. Are there contexts where bullets are ok?"},
            {"role": "user", "content": "Tables are fine for comparisons. Bullet lists for tasks or steps. But never use bullets to present conclusions or reasoning — that flattens the thinking."},
            {"role": "assistant", "content": "Makes sense. How about response length?"},
            {"role": "user", "content": "Keep it short unless I ask for depth. I read fast and I'll ask follow-ups. Padding wastes both our time."},
            {"role": "assistant", "content": "Understood. Any other preferences?"},
            {"role": "user", "content": "I appreciate when you push back on my assumptions. Don't just agree with me — if I'm wrong, say so directly."},
        ],
        "must_capture": ["prefers structured prose over bullets", "short responses unless depth requested", "wants direct pushback when wrong"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-003",
        "label": "product-decisions",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "We decided today to drop the mobile app from v1. Too much scope."},
            {"role": "assistant", "content": "That's a significant scope cut. What's the v1 scope now?"},
            {"role": "user", "content": "Web only. Progressive web app so mobile users can still use it in browser. We'll revisit native after first paying customers."},
            {"role": "assistant", "content": "Good call. Any other scope decisions?"},
            {"role": "user", "content": "We also deferred the API marketplace. The core product needs to be stable before we open it to third parties."},
            {"role": "assistant", "content": "That protects the platform. What's the timeline on core stability?"},
            {"role": "user", "content": "We want 5 paying customers before opening the marketplace. That's the gate."},
        ],
        "must_capture": ["dropped mobile app from v1", "web-only with PWA fallback", "5 paying customers gate before marketplace"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-004",
        "label": "working-rhythm",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "I work best in the mornings. By 2pm my thinking degrades and I switch to mechanical tasks."},
            {"role": "assistant", "content": "Good to know. Do you have a consistent schedule?"},
            {"role": "user", "content": "I deep work from 8am to noon. No meetings, no Slack. Afternoons are for meetings and reviews."},
            {"role": "assistant", "content": "That's a strong system. Do you prefer async or sync collaboration?"},
            {"role": "user", "content": "Strongly async. I hate being pulled into calls unless it's genuinely a conversation that can't happen over text. Most things can."},
        ],
        "must_capture": ["deep work 8am-noon, no interruptions", "strongly prefers async collaboration"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-005",
        "label": "technical-standards",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "One thing I've learned: never commit directly to main. It seems obvious but I've seen too many broken builds."},
            {"role": "assistant", "content": "What's your branch strategy?"},
            {"role": "user", "content": "Feature branches, always. PR required even for solo projects — it forces me to write a description before I merge."},
            {"role": "assistant", "content": "Do you have a particular commit message style?"},
            {"role": "user", "content": "Conventional commits. feat, fix, refactor, docs, chore. I find it makes git log actually useful for changelogs."},
            {"role": "assistant", "content": "Any other non-negotiables?"},
            {"role": "user", "content": "Tests. I don't merge anything without tests. The coverage target is 80% minimum; I've never gone below it in five years."},
        ],
        "must_capture": ["feature branches + PR required", "conventional commit messages", "80% test coverage minimum"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-006",
        "label": "decision-framework",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "When I'm making a product decision, I always start with: what does the user have to do right now that they can't do? Not what would be nice."},
            {"role": "assistant", "content": "Jobs-to-be-done framing?"},
            {"role": "user", "content": "Exactly. I've been burned by building things that seemed compelling but weren't blocking anyone. Blocking problems get shipped first."},
            {"role": "assistant", "content": "How do you weigh urgency vs impact?"},
            {"role": "user", "content": "Impact first, always. Urgency is usually manufactured. When I feel urgent, I ask: who actually can't make progress because of this? If the answer is vague, I don't rush."},
        ],
        "must_capture": ["starts with blocking user problems, not nice-to-haves", "impact over urgency"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-007",
        "label": "company-context",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "We're a 3-person team right now: me (CEO), a senior engineer, and a designer."},
            {"role": "assistant", "content": "Early stage. What's your current ARR?"},
            {"role": "user", "content": "Pre-revenue. We're building toward a beta launch in Q3."},
            {"role": "assistant", "content": "Who's the target customer?"},
            {"role": "user", "content": "Mid-market B2B SaaS companies. Specifically head of product or VP product at companies with 50–200 employees. They're our primary buyer."},
            {"role": "assistant", "content": "What's the core pain you're solving?"},
            {"role": "user", "content": "Context loss between meetings. They have great conversations, then 80% of the decisions made don't get executed because nobody has a reliable system to track them."},
        ],
        "must_capture": ["3-person team: CEO + engineer + designer", "target: VP product at 50-200 person companies", "pain: context loss between meetings"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-008",
        "label": "feedback-preferences",
        "category": "factual",
        "messages": [
            {"role": "user", "content": "I prefer written feedback over verbal. I can't process criticism in real-time — I need to sit with it."},
            {"role": "assistant", "content": "That's very common. Any particular format?"},
            {"role": "user", "content": "Specific over general. Tell me exactly what's wrong, not just 'this doesn't feel right'. I can handle blunt feedback, I just need it to be precise."},
            {"role": "assistant", "content": "Makes sense. What about positive feedback?"},
            {"role": "user", "content": "I'm skeptical of generic praise. If you're going to say something is good, say why it's good. Otherwise I assume it's a warmup before the criticism."},
        ],
        "must_capture": ["prefers written over verbal feedback", "specific/precise feedback over general", "skeptical of generic praise"],
        "must_not_hallucinate": True,
    },

    # ── Category B: Opinion / preference-heavy (3 conversations) ───────────

    {
        "id": "conv-009",
        "label": "frameworks-opinions",
        "category": "opinion",
        "messages": [
            {"role": "user", "content": "What do you think about microservices for early-stage startups?"},
            {"role": "assistant", "content": "Generally premature in my view — the coordination overhead rarely pays off until you have teams that need to deploy independently."},
            {"role": "user", "content": "I agree completely. I started with a microservices architecture once and regretted it for 18 months. We had 8 services before we had 10 users."},
            {"role": "assistant", "content": "Classic premature optimization. What would you do differently now?"},
            {"role": "user", "content": "Monolith first, always. With clean module boundaries so you can extract later if you really need to. But 90% of the time you won't need to."},
            {"role": "assistant", "content": "That's the pragmatic path. Next.js monorepo gets you surprisingly far."},
            {"role": "user", "content": "Exactly. I'm not religious about any stack but I have strong opinions about not over-engineering early."},
        ],
        "must_capture": ["prefers monolith-first for early-stage, extract later if needed", "has been burned by premature microservices"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-010",
        "label": "task-prioritization-opinions",
        "category": "opinion",
        "messages": [
            {"role": "user", "content": "I'm trying to figure out whether to focus on growth or product depth next quarter."},
            {"role": "assistant", "content": "What's driving the question — investor pressure, churn, or something else?"},
            {"role": "user", "content": "Mainly our retention isn't great. About 40% of signups don't come back after the first week."},
            {"role": "assistant", "content": "Then depth is probably right — growth brings in more people who churn immediately."},
            {"role": "user", "content": "That's my instinct too. But our board wants to see user numbers move."},
            {"role": "assistant", "content": "There's a case to be made for fixing retention first. What's causing the drop-off?"},
            {"role": "user", "content": "We think it's the onboarding — too many steps before you get any value. We need to cut it to 3 steps maximum."},
        ],
        "must_capture": ["40% week-1 churn problem", "wants to cut onboarding to 3 steps max"],
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-011",
        "label": "meeting-preferences",
        "category": "opinion",
        "messages": [
            {"role": "user", "content": "I find most status meetings completely pointless. Write a Loom, send a Notion doc."},
            {"role": "assistant", "content": "Which meetings do you find valuable?"},
            {"role": "user", "content": "Decisions. If there's a decision to make that requires two people, that's worth a call. Anything else is async."},
            {"role": "assistant", "content": "What about 1:1s?"},
            {"role": "user", "content": "Monthly is enough for me. Weekly 1:1s feel like overhead theater unless someone's struggling."},
        ],
        "must_capture": ["meetings only for decisions requiring real-time input", "monthly 1:1 cadence preference"],
        "must_not_hallucinate": True,
    },

    # ── Category C: Task-focused / low personal content (3 conversations) ──

    {
        "id": "conv-012",
        "label": "debugging-session",
        "category": "task",
        "messages": [
            {"role": "user", "content": "I'm getting a 422 on my Pydantic validation endpoint. Here's the error: field required [name]"},
            {"role": "assistant", "content": "That means the request body doesn't include `name`. Is it in the payload?"},
            {"role": "user", "content": "Oh wait, I was sending `full_name` instead of `name`. My mistake."},
            {"role": "assistant", "content": "Easy fix! Pydantic is strict about field names by default."},
            {"role": "user", "content": "Fixed. Thanks. The endpoint is working now."},
        ],
        "must_capture": [],  # Pure debugging session — nothing worth persisting
        "expected_sparse": True,
    },

    {
        "id": "conv-013",
        "label": "sql-query-help",
        "category": "task",
        "messages": [
            {"role": "user", "content": "Can you write a SQL query to count active users per day for the last 30 days?"},
            {"role": "assistant", "content": "Sure. Assuming a `sessions` table with `user_id` and `created_at`:\n```sql\nSELECT DATE(created_at) as date, COUNT(DISTINCT user_id) as active_users\nFROM sessions\nWHERE created_at >= NOW() - INTERVAL '30 days'\nGROUP BY DATE(created_at)\nORDER BY date;\n```"},
            {"role": "user", "content": "Perfect. What if I want to filter to only users who logged in more than once that day?"},
            {"role": "assistant", "content": "Add a HAVING clause:\n```sql\nHAVING COUNT(user_id) > 1\n```"},
            {"role": "user", "content": "Got it. Thanks."},
        ],
        "must_capture": [],  # Mechanical SQL help — nothing worth persisting
        "expected_sparse": True,
    },

    {
        "id": "conv-014",
        "label": "grammar-check",
        "category": "task",
        "messages": [
            {"role": "user", "content": "Can you fix the grammar in this sentence: 'The users which uses our product daily is very important to us.'"},
            {"role": "assistant", "content": "'The users who use our product daily are very important to us.'"},
            {"role": "user", "content": "Great, thanks."},
        ],
        "must_capture": [],  # Trivial single-turn grammar check
        "expected_sparse": True,
    },

    # ── Category D: Contradicting statements (2 conversations) ─────────────

    {
        "id": "conv-015",
        "label": "stack-contradiction",
        "category": "contradiction",
        "messages": [
            {"role": "user", "content": "We're planning to use TypeScript for the backend. I'm tired of Python's type system."},
            {"role": "assistant", "content": "Node.js + TypeScript backend? That's a solid stack."},
            {"role": "user", "content": "Actually — I've been thinking more. The rest of the team knows Python and we have a lot of Python tooling. We're sticking with FastAPI."},
            {"role": "assistant", "content": "Makes sense given the team context. Python + FastAPI it is."},
            {"role": "user", "content": "Final decision: Python backend, TypeScript frontend. Clear boundary."},
        ],
        "must_capture": ["Python backend (FastAPI), TypeScript frontend — clear boundary"],
        "must_capture_latest": True,  # Latest statement wins
        "must_not_hallucinate": True,
    },

    {
        "id": "conv-016",
        "label": "timeline-update",
        "category": "contradiction",
        "messages": [
            {"role": "user", "content": "We were targeting a Q2 launch but honestly that's not realistic."},
            {"role": "assistant", "content": "What's the new target?"},
            {"role": "user", "content": "We pushed to Q3. August 15 is the hard date we committed to investors."},
            {"role": "assistant", "content": "That's 8 weeks of buffer from June. Achievable if scope is locked."},
            {"role": "user", "content": "Scope is locked. No new features until after launch."},
        ],
        "must_capture": ["launch date August 15 (Q3), committed to investors", "scope locked — no new features pre-launch"],
        "must_capture_latest": True,
        "must_not_hallucinate": True,
    },

    # ── Category E: Very short conversations (<5 exchanges) (2 conversations) ─

    {
        "id": "conv-017",
        "label": "short-preference-mention",
        "category": "short",
        "messages": [
            {"role": "user", "content": "I use Cursor for all my coding. Claude is my main model there."},
            {"role": "assistant", "content": "Good combo. Cursor + Claude Sonnet is fast."},
        ],
        "must_capture": ["uses Cursor IDE with Claude as primary model"],
        "must_not_hallucinate": True,
    },

]
