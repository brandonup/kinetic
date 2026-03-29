"""
Synthetic document fixtures for Linked Upload extraction eval (KIN-328).

30 documents: 10 per surface (User Profile, Company, Agent).
Each has: document text, expected extraction output, and scoring hints.

Name precision: exact string match (normalized: strip, lowercase).
Relevance scoring (1-3 rubric applied by judge):
  1 = poor — missing key information or significantly inaccurate
  2 = acceptable — captures main points but imprecise or missing some context
  3 = good — accurate, complete, captures the right level of detail
"""

# ---------------------------------------------------------------------------
# Surface 1: User Profile documents (extract: name + bio)
# Expected: name precision ≥ 85%, bio relevance ≥ 2.0/3.0
# ---------------------------------------------------------------------------

USER_PROFILE_DOCS = [

    {
        "id": "user-001",
        "label": "software-engineer-linkedin",
        "text": """Sarah Chen
Senior Software Engineer at Stripe
San Francisco, CA

I'm a senior software engineer at Stripe where I work on distributed systems for payment processing.
I've spent the last 8 years building high-availability infrastructure — specifically around consensus
protocols, distributed transactions, and observability tooling. Before Stripe I was at Google on the
Spanner team. I care deeply about reliability engineering and have strong opinions about error budgets
and SLO-based on-call rotations. When I'm not writing Go, I'm usually mentoring junior engineers or
contributing to open-source distributed systems projects.""",
        "expected": {
            "name": "Sarah Chen",
            "bio_keywords": ["software engineer", "distributed systems", "Stripe", "reliability", "Go"],
        },
    },

    {
        "id": "user-002",
        "label": "product-manager-cv",
        "text": """Marcus Williams
Product Manager | B2B SaaS | 0→1 Builder

Marcus Williams is a product manager with 10 years of experience building 0-to-1 B2B SaaS products.
He currently leads product at a Series A fintech startup focused on automated spend management for
mid-market companies. Previously at HubSpot, where he shipped the deal forecasting product, and
McKinsey, where he led digital transformation engagements in financial services. Marcus is known
for his quantitative approach to roadmap prioritization and his obsession with reducing time-to-value
for new users. He holds an MBA from Kellogg and a BSc in Statistics from Michigan.""",
        "expected": {
            "name": "Marcus Williams",
            "bio_keywords": ["product manager", "B2B SaaS", "fintech", "HubSpot", "roadmap"],
        },
    },

    {
        "id": "user-003",
        "label": "founder-bio",
        "text": """Alex Rivera | Founder & CEO

I'm the founder of Lumina AI, a company building context-aware AI tools for knowledge workers.
Before starting Lumina, I was CTO at a Series B HR tech company for 4 years, and before that
a founding engineer at two YC startups (one acquired, one still running). My background is in
ML infrastructure — specifically model serving and evaluation pipelines. I'm technical enough
to write production code but I've shifted into full-time product/company building. I care about
AI that actually works in production, not demos.""",
        "expected": {
            "name": "Alex Rivera",
            "bio_keywords": ["founder", "Lumina AI", "CTO", "ML infrastructure", "AI"],
        },
    },

    {
        "id": "user-004",
        "label": "designer-about-page",
        "text": """Priya Nair — Design Lead

I lead design at a Series B consumer app with 2M users. My background is in interaction design and
systems thinking — I trained at RISD and spent 3 years at IDEO before moving into the startup world.
I specialize in designing for complex information environments: dashboards, data tools, and anything
where the UI needs to handle expert users without overwhelming novices. I publish occasionally on
Substack about design systems and accessibility in enterprise software.""",
        "expected": {
            "name": "Priya Nair",
            "bio_keywords": ["design", "RISD", "IDEO", "interaction design", "accessibility"],
        },
    },

    {
        "id": "user-005",
        "label": "vc-partner-bio",
        "text": """THOMAS BERG
Partner, Sequoia Capital

Thomas Berg is a Partner at Sequoia Capital focused on enterprise software and developer tools.
He joined Sequoia after 12 years as an operator — most recently as SVP Engineering at Salesforce,
where he led the platform infrastructure team through two major acquisitions. Thomas has led
investments in 14 companies to date and sits on the boards of Retool, Notion, and three other
enterprise software companies. He has a PhD in Computer Science from Carnegie Mellon (distributed
systems focus) and an undergrad from MIT.""",
        "expected": {
            "name": "Thomas Berg",
            "bio_keywords": ["Sequoia", "partner", "enterprise software", "Salesforce", "investments"],
        },
    },

    {
        "id": "user-006",
        "label": "researcher-profile",
        "text": """Dr. Yuki Tanaka
Research Scientist, AI Safety

I'm a research scientist specializing in AI alignment and interpretability. My current work focuses
on mechanistic interpretability of large language models — specifically, understanding how attention
heads encode factual recall. I completed my PhD at MIT (CSAIL) in 2022 and did a postdoc at
Anthropic before joining a university AI safety lab. I care about publishing clearly accessible
research and bridging academic and industry work on AI safety. I occasionally write public
explainers for non-technical audiences.""",
        "expected": {
            "name": "Yuki Tanaka",
            "bio_keywords": ["AI alignment", "interpretability", "MIT", "research scientist", "language models"],
        },
    },

    {
        "id": "user-007",
        "label": "consultant-bios",
        "text": """DIANA OKONKWO
Independent Consultant | Revenue Operations

Diana Okonkwo helps growth-stage B2B companies build scalable revenue operations systems.
She has worked with 40+ companies in the $5M-$50M ARR range, specializing in CRM implementation,
sales process design, and analytics infrastructure. Before consulting, she spent 5 years as
Director of Sales Operations at a public SaaS company. Diana is known for cutting time-to-close
by 20-30% through better data hygiene and process automation. She works with 5-6 clients at a
time and does not take on early-stage companies without product-market fit.""",
        "expected": {
            "name": "Diana Okonkwo",
            "bio_keywords": ["revenue operations", "consultant", "CRM", "B2B", "sales"],
        },
    },

    {
        "id": "user-008",
        "label": "journalist-profile",
        "text": """Ben Kowalski | Technology Journalist

I cover AI, enterprise software, and the business of tech for The Information. I've been a
technology journalist for 12 years, previously at TechCrunch and Wired. My focus is on the
intersection of AI adoption and organizational change — specifically how companies are actually
(not theoretically) integrating AI into their workflows. I'm based in New York and speak at
industry conferences 3-4 times a year. I have a BA in Economics from Yale.""",
        "expected": {
            "name": "Ben Kowalski",
            "bio_keywords": ["journalist", "AI", "enterprise software", "The Information", "TechCrunch"],
        },
    },

    {
        "id": "user-009",
        "label": "short-linkedin-bio",
        "text": """Jamie Cortez - Staff Engineer @ Airbnb | Previously Meta, Uber

Building infrastructure that scales. Interested in distributed systems, platform engineering,
and developer experience. 12 years in the industry, currently working on Airbnb's ML platform.""",
        "expected": {
            "name": "Jamie Cortez",
            "bio_keywords": ["staff engineer", "Airbnb", "distributed systems", "ML platform"],
        },
    },

    {
        "id": "user-010",
        "label": "no-clear-author",  # Edge: document has no clear individual author
        "text": """Annual Report — Acme Corp 2024

Executive Summary: Acme Corp delivered record results in fiscal year 2024, with revenue growing
32% year-over-year to $450M. The company expanded into three new markets and launched four major
product lines. Our team of 1,200 employees across 8 countries remained focused on our mission of
simplifying complex enterprise workflows.""",
        "expected": {
            "name": None,  # No individual author — should return null
            "bio_keywords": [],  # Bio may be null or minimal
        },
        "edge_case": "no_individual_author",
    },

]


# ---------------------------------------------------------------------------
# Surface 2: Company documents (extract: name + description)
# Expected: name precision ≥ 85%, description relevance ≥ 2.0/3.0
# ---------------------------------------------------------------------------

COMPANY_DOCS = [

    {
        "id": "company-001",
        "label": "saas-one-pager",
        "text": """Lattice — People Management Platform

Lattice helps HR and People teams build a high-performance culture through continuous performance
management, goals, and engagement. Over 5,000 companies use Lattice to run performance reviews,
set OKRs, and measure employee engagement. The platform integrates with Slack, HRIS systems,
and calendar tools to fit into existing workflows. Lattice customers see 3x improvement in
manager effectiveness scores within 6 months of deployment.""",
        "expected": {
            "name": "Lattice",
            "description_keywords": ["HR", "performance management", "OKRs", "engagement", "5,000 companies"],
        },
    },

    {
        "id": "company-002",
        "label": "early-stage-pitch",
        "text": """Meridian AI
Series A | $8M Raised

The Problem: Customer success teams at B2B SaaS companies spend 60% of their time on manual
reporting and status updates — time that should go into actual customer relationships.

Our Solution: Meridian AI automates customer health scoring and proactive outreach using
your existing CRM data. No new data sources required. 10-minute setup.

Traction: 45 paying customers, $500K ARR, 140% net revenue retention.
Team: 8 people, based in Austin TX.""",
        "expected": {
            "name": "Meridian AI",
            "description_keywords": ["customer success", "B2B SaaS", "AI", "health scoring", "CRM"],
        },
    },

    {
        "id": "company-003",
        "label": "about-page",
        "text": """About Northstar Security

Northstar Security is a cybersecurity firm specializing in penetration testing and security
compliance for fintech and healthcare companies. Founded in 2015, we've helped over 200
companies achieve SOC 2 Type II, HIPAA compliance, and PCI DSS certification. Our team of
35 certified security engineers combines offensive security expertise with a pragmatic
compliance advisory approach. We believe that security done right is a competitive advantage,
not a checkbox exercise.""",
        "expected": {
            "name": "Northstar Security",
            "description_keywords": ["cybersecurity", "penetration testing", "fintech", "compliance", "SOC 2"],
        },
    },

    {
        "id": "company-004",
        "label": "investor-memo",
        "text": """Flux — Infrastructure for AI Applications
Seed Stage | Founded 2023

Flux provides the infrastructure layer for teams building production AI applications.
Core product: a managed pipeline orchestration service that handles prompt versioning,
model routing, observability, and cost optimization across OpenAI, Anthropic, and
open-source models. Target customer: engineering teams at companies with 10-200 engineers
who are moving from prototype to production. Current stage: 120 design partners,
launching paid plans in Q2.""",
        "expected": {
            "name": "Flux",
            "description_keywords": ["AI infrastructure", "pipeline orchestration", "prompt versioning", "observability"],
        },
    },

    {
        "id": "company-005",
        "label": "press-release",
        "text": """FOR IMMEDIATE RELEASE

Greenleaf Logistics Expands to European Market

CHICAGO, IL — Greenleaf Logistics, a leading provider of last-mile delivery optimization
software for e-commerce retailers, today announced its expansion into the European market
with new operations in Germany and the Netherlands. Greenleaf's platform helps retailers
reduce delivery costs by 18-25% through AI-powered route optimization and carrier selection.
The company currently serves 1,200 retailers across North America processing 40 million
deliveries annually.""",
        "expected": {
            "name": "Greenleaf Logistics",
            "description_keywords": ["last-mile delivery", "e-commerce", "route optimization", "retail"],
        },
    },

    {
        "id": "company-006",
        "label": "product-hunt-launch",
        "text": """Introducing Copywright AI 🚀

We're Copywright AI — the writing assistant built specifically for growth teams.
Unlike generic AI writers, Copywright is trained on 50M+ high-converting ads,
landing pages, and email campaigns. It understands brand voice, A/B testing,
and conversion metrics. Features: tone calibration, competitor gap analysis,
multi-variant generation, and direct integration with Google Ads and Meta Ads.
Built by the team behind AdMetrics (acquired by HubSpot in 2022).""",
        "expected": {
            "name": "Copywright AI",
            "description_keywords": ["AI writing", "growth", "ads", "landing pages", "conversion"],
        },
    },

    {
        "id": "company-007",
        "label": "linkedin-company-page",
        "text": """Vantage Point Analytics
501-1000 employees | Founded 2014 | San Francisco

Vantage Point Analytics provides market intelligence and competitive analysis software for
enterprise sales teams. Our platform aggregates signals from 200+ data sources to give
sales teams real-time visibility into accounts, competitors, and market movements.
Customers include Salesforce, Adobe, and Oracle. Named to Forbes Cloud 100 for three
consecutive years. Our mission: give every sales professional the information advantage
of a world-class analyst.""",
        "expected": {
            "name": "Vantage Point Analytics",
            "description_keywords": ["market intelligence", "competitive analysis", "enterprise sales", "Salesforce"],
        },
    },

    {
        "id": "company-008",
        "label": "bootstrap-company",
        "text": """Pixel & Thread Studio

We're a small independent design studio of 4 people, building design systems and
brand identity work for Series A-C startups. We don't do websites. We don't do
ad creative. We do one thing: help early-stage companies build design systems
that scale with them. Our typical engagement is 8 weeks and produces a complete
design system with Figma components, documentation, and a 2-hour handoff session.""",
        "expected": {
            "name": "Pixel & Thread Studio",
            "description_keywords": ["design studio", "design systems", "brand identity", "startups", "Figma"],
        },
    },

    {
        "id": "company-009",
        "label": "nonprofit-overview",
        "text": """Code Forward — About Us

Code Forward is a nonprofit that trains and places underrepresented youth in software
engineering careers. Since 2016, we've run 18-month intensive programs combining technical
skills, professional development, and job placement support. To date, 94% of our 600
graduates have found software engineering roles with a median starting salary of $85K.
We operate in 8 cities and are expanding to 5 more. Funding comes from corporate partners
including Google, Microsoft, and Stripe.""",
        "expected": {
            "name": "Code Forward",
            "description_keywords": ["nonprofit", "software engineering", "training", "youth", "placement"],
        },
    },

    {
        "id": "company-010",
        "label": "ambiguous-company-name",  # Edge: name appears multiple times in context
        "text": """Introducing our new platform: Atlas

The team at Meridian Group is excited to announce Atlas, our new enterprise data platform.
Meridian Group has been building data infrastructure for Fortune 500 companies since 2010,
and Atlas represents our next-generation product. Atlas connects 500+ data sources, provides
real-time transformation, and integrates natively with dbt, Airflow, and Fivetran.""",
        "expected": {
            "name": "Meridian Group",  # The company name, not the product name
            "description_keywords": ["data platform", "enterprise", "Fortune 500", "Atlas"],
        },
        "edge_case": "product_vs_company_name",
    },

]


# ---------------------------------------------------------------------------
# Surface 3: Agent corpus documents (extract: name + instructions/system prompt)
# Expected: name plausibility (not exact match), instructions coverage ≥ 2.0/3.0
# ---------------------------------------------------------------------------

AGENT_CORPUS_DOCS = [

    {
        "id": "agent-001",
        "label": "paul-graham-essays",
        "text": """Excerpts from essays on startups and technology.

What I tell founders: do things that don't scale. When you're small, you can give every
user a level of attention that a big company never could. Use that. The goal isn't to find
a scalable solution; it's to find what works, then figure out how to scale it.

Most people don't realize that the fastest way to grow is to retain the users you have.
Churn is the silent killer of startups. A leaky bucket fills no one.

The best founders I know are obsessively focused on making something people want — not
something they think people should want. There's a big difference. Customers vote with
dollars, not opinions.

On advice: most advice is bad. Not because advisors are stupid, but because they're
pattern-matching to their own experience which may not apply to you. Take advice seriously
only from people who have done exactly what you're trying to do.

Startups die of starvation, not indigestion. The biggest danger isn't doing too little —
it's taking on too much at once and executing badly across the board.""",
        "expected": {
            "name_plausible": ["Paul Graham", "PG", "Graham"],  # Any of these acceptable
            "instructions_must_cover": ["things that don't scale", "retention over growth", "making something people want", "skeptical of advice"],
        },
    },

    {
        "id": "agent-002",
        "label": "naval-ravikant-tweetstorm",
        "text": """Collected thoughts on wealth, leverage, and compounding.

Seek wealth, not money or status. Wealth is having assets that earn while you sleep.

Specific knowledge is knowledge you cannot be trained for. If society can train you for
it, society can also replace you with someone else. Arm yourself with specific knowledge,
accountability, and leverage.

The most important form of leverage is code and media. Both have near-zero marginal cost
for reproduction. You create it once and it works while you sleep.

Judgment and decision-making are the highest-leverage skills in the modern economy.
You can outsource almost everything else, but not your judgment.

Play long-term games with long-term people. All returns in life — wealth, relationships,
knowledge — come from compound interest. Short-term thinking is the enemy.""",
        "expected": {
            "name_plausible": ["Naval Ravikant", "Naval"],
            "instructions_must_cover": ["specific knowledge", "leverage", "compounding", "judgment"],
        },
    },

    {
        "id": "agent-003",
        "label": "andy-grove-management",
        "text": """Notes on high output management.

The output of a manager is the output of the organizational units under their supervision
or influence. Never forget that. Your job is to multiply leverage through your team.

Meetings are a form of work, not a break from it. But most meetings are badly run.
A well-run one-on-one with a direct report should surface problems while they're still
small. The manager's job is to create the conditions for their team to do great work.

Task-relevant maturity determines how much supervision to provide. A new employee doing
a familiar task needs structured guidance. An experienced employee facing a new challenge
needs support and collaboration. Same person, different tasks, different management style.

Measure everything that matters. Indicators should be black-box: they should reflect
outcomes, not activities. If you're measuring the wrong thing, you're creating the wrong
incentives.""",
        "expected": {
            "name_plausible": ["Andy Grove", "Grove", "Andrew Grove"],
            "instructions_must_cover": ["manager output", "one-on-ones", "task-relevant maturity", "measurement"],
        },
    },

    {
        "id": "agent-004",
        "label": "ben-horowitz-blog",
        "text": """The Hard Thing About Hard Things — selected passages.

There's no recipe for being a great CEO. What I've learned: the only thing that prepares
you for running a company is running a company. Most of what you'll face won't be covered
in any book or case study.

When everything is going wrong — and it will — the most important thing is not to fall
apart. Your team takes its emotional cues from you. Stay calm, focused, and honest.
You can be scared, but you cannot let the fear drive your decisions.

Lay off with care and respect. If you have to do it, do it once, do it decisively, and
give people the dignity of a clear explanation and generous terms. A layoff done badly
leaves a scar on the company culture that takes years to heal.

Hire for strength, not the absence of weakness. Everybody has weaknesses. The question
is whether their strengths are extraordinary and their weaknesses are manageable.""",
        "expected": {
            "name_plausible": ["Ben Horowitz", "Horowitz"],
            "instructions_must_cover": ["no recipe for CEO", "emotional leadership", "hiring for strength"],
        },
    },

    {
        "id": "agent-005",
        "label": "ryan-holiday-stoicism",
        "text": """Excerpts on Stoicism and practical philosophy.

The obstacle is the way. Every impediment to action advances action. What stands in the
way becomes the way. The Stoics didn't say problems don't exist — they said your
perception of them is within your control, and that control is everything.

You have power over your mind, not outside events. Realize this, and you will find strength.
Focus on what you control: your actions, your reactions, your judgments. Let go of
what you cannot control, and stop wasting energy trying.

Memento mori — remember you will die. This isn't morbid. It's clarifying. When you
remember that your time is finite, trivialities fall away and what matters becomes obvious.

Practice negative visualization daily. Imagine losing what you have. This isn't pessimism —
it's preparation. The Stoic who has contemplated loss is not destroyed when it arrives.""",
        "expected": {
            "name_plausible": ["Ryan Holiday", "Holiday"],
            "instructions_must_cover": ["obstacle is the way", "control over mind", "stoicism", "memento mori"],
        },
    },

    {
        "id": "agent-006",
        "label": "charity-majors-observability",
        "text": """Thoughts on modern observability and engineering culture.

Observability isn't about dashboards. It's about being able to ask arbitrary questions
about your production systems without shipping new code. If you need a new dashboard to
understand a new failure mode, your observability is insufficient.

The goal of on-call is to be boring. If you're heroically fighting fires, you've already
failed. Good systems make problems visible and tractable before they become incidents.

Every engineer should be on-call for what they ship. There's no faster feedback loop than
being woken up at 3am by your own code. Empathy for users and operational empathy are the
same thing viewed from different angles.

Ship incrementally and measure everything. Dark launches, canaries, feature flags —
these aren't just deployment patterns. They're epistemological tools for understanding
how your software actually behaves in the wild.""",
        "expected": {
            "name_plausible": ["Charity Majors", "Majors"],
            "instructions_must_cover": ["observability", "on-call", "production systems", "incremental shipping"],
        },
    },

    {
        "id": "agent-007",
        "label": "first-person-essay-explicit-name",
        "text": """My Framework for Prioritization — by James Okafor

I've spent 15 years in product management, and I keep coming back to one truth: most
teams don't have a prioritization problem, they have a clarity problem. They don't know
what they're trying to achieve, so everything looks equally important.

My process: write down the single most important thing the company needs to accomplish
in the next 6 months. Not three things. One. Then work backwards from that to identify
what must be true for it to happen. That becomes your decision filter.

When I'm evaluating whether to build something, I ask: which user is blocked from
achieving their goal right now because this doesn't exist? If I can name them specifically,
it's worth doing. If I can only describe them hypothetically, it probably isn't.""",
        "expected": {
            "name_plausible": ["James Okafor"],
            "instructions_must_cover": ["clarity over prioritization", "single most important goal", "blocked user test"],
        },
    },

    {
        "id": "agent-008",
        "label": "ux-design-principles",
        "text": """Don Norman on Design — compiled principles.

Good design is invisible. When design works, you don't notice it — you just accomplish
your goal. The moment a user has to think about how to use an interface, the design has
failed at some level.

Affordances communicate what actions are possible. Signifiers tell you where to take action.
Feedback tells you what happened. Constraints prevent errors. Get these right and your
product works. Get them wrong and you'll spend years blaming users for 'not getting it.'

Complexity is not inherently bad. Complicated is bad. A flight simulator should be complex —
it needs to reflect a complex reality. But its complexity should be logical, consistent,
and learnable. Complicated means arbitrary. Complicated is a design failure.""",
        "expected": {
            "name_plausible": ["Don Norman", "Norman"],
            "instructions_must_cover": ["invisible design", "affordances", "feedback", "complexity vs complicated"],
        },
    },

    {
        "id": "agent-009",
        "label": "multi-author-essay",  # Edge: document has multiple contributors
        "text": """Building for Trust — A Collaboration

Written by the Product Ethics team at OpenAI.

When we design AI products, trust isn't a feature — it's the foundation. Users extend
trust on the basis of consistency, transparency, and demonstrated competence. Every
time the system behaves unpredictably, trust is depleted.

The biggest mistake teams make is treating safety as a constraint rather than a design
goal. Safety-first products aren't safer by accident. They're safer because the team
asked 'what could go wrong?' before 'what should we build?'

User agency is essential. People are more forgiving of mistakes when they understand
what happened and have a path to correct it. Error states are opportunities for
rebuilding trust, not just for damage control.""",
        "expected": {
            "name_plausible": ["OpenAI", "Product Ethics", None],  # Multiple acceptable
            "instructions_must_cover": ["trust", "safety-first", "user agency", "transparency"],
        },
        "edge_case": "multi_author",
    },

    {
        "id": "agent-010",
        "label": "very-short-corpus",  # Edge: very short document
        "text": """Be direct. Cut the fluff. Say what you mean and mean what you say.
Prefer concrete examples over abstractions. Always ask: does this actually help the
person I'm talking to?""",
        "expected": {
            "name_plausible": [None],  # No clear author
            "instructions_must_cover": ["direct communication", "concrete examples"],
        },
        "edge_case": "very_short",
    },

]
