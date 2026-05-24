"""
Prompt registry — versioned prompt templates for LLM-powered features.

Convention: conventions.md §GenAI — no hardcoded prompts in application logic.
Every prompt gets an ID and version. Changes produce a traceable diff.

Usage:
    from app.services.prompts import get_prompt

    text = get_prompt("generate-user-profile-v1", "name_extract")
"""

from typing import Any

# ---------------------------------------------------------------------------
# Registry: {prompt_id: {field: prompt_text}}
# ---------------------------------------------------------------------------

PROMPTS: dict[str, dict[str, Any]] = {
    # -----------------------------------------------------------------------
    # Linked Upload — User Profile extraction (KIN-310)
    # -----------------------------------------------------------------------
    "generate-user-profile-v1": {
        "name_extract": (
            "Extract the person's full name from this document. "
            "Return only the name — no additional text. "
            "If no individual person can be identified as the author "
            "(e.g., a company blog post, team page, or unsigned document), "
            "return null. Do not guess or fabricate a name. "
            "If the name cannot be determined, return null."
        ),
        "bio_extract": (
            "Generate a concise professional bio (2-4 sentences, max 1000 characters) "
            "based on the person's current role, professional background, and domain "
            "expertise as described in the document. Write in first person. Do not include "
            "specific company names, dates, or metrics unless essential to context."
        ),
    },
    # -----------------------------------------------------------------------
    # Linked Upload — Company Profile extraction (KIN-310)
    # -----------------------------------------------------------------------
    "generate-company-profile-v1": {
        "name_extract": (
            "Extract the company name from the document. "
            "Return the shortest canonical company name only. "
            "Strip taglines, slogans, emojis, 'About' prefixes, "
            "'Introducing' preamble, and any decorative text. "
            "If ambiguous or not found, return null."
        ),
        "description_extract": (
            "Generate a concise company description (2-4 sentences, max 1000 characters) "
            "covering what the company does, who it serves, and what makes it distinctive. "
            "Base this only on the document content. Write in third person."
        ),
    },
    # -----------------------------------------------------------------------
    # Linked Upload — Agent Persona extraction (KIN-311)
    # -----------------------------------------------------------------------
    "generate-agent-persona-v1": {
        "name_extract": (
            "Identify the primary author, speaker, or thought leader in this document. "
            "Return their full name only — no additional text. "
            "If the document has no clear single author, return the most prominent name. "
            "If no name can be determined, return null."
        ),
        "instructions_extract": (
            "You are building a system prompt for an AI agent that thinks and reasons "
            "like the person whose writing is provided below. Analyze the document for: "
            "(1) thinking style, (2) communication patterns, (3) core principles, "
            "(4) areas of expertise, (5) distinctive perspective. "
            "Generate a system prompt (300–500 tokens) written as instructions to an LLM. "
            "The prompt should begin with 'You are [name]...' and instruct the model to "
            "adopt this person's reasoning style, principles, and communication patterns. "
            "Do not simply summarize the document."
        ),
    },
    # -----------------------------------------------------------------------
    # Context Stack — System prompt for chat generation (KIN-385)
    # -----------------------------------------------------------------------
    "context-stack-system-v1": {
        "system": (
            "You are a helpful AI assistant. Use the context provided below to inform your responses. "
            "Always prioritize information from the context layers when relevant to the user's question.\n\n"
            "{context_layers}\n\n"
            "{rag_context}"
        ),
    },
    # -----------------------------------------------------------------------
    # Context Stack — Date-aware system prompt (KIN-485, Component D)
    #
    # Used by generation.py when `settings.RECENCY_ENABLED=True`. Identical to
    # v1 plus the recency / contradiction-preference instruction below. The
    # ``Sources are labeled with publication dates`` framing matches what
    # context_assembler.py emits — ``[Source: TITLE, Published: YYYY-MM-DD]``
    # for real dates, ``Added: YYYY-MM-DD`` for ingestion-date fallbacks.
    # -----------------------------------------------------------------------
    "context-stack-system-v2": {
        "system": (
            "You are a helpful AI assistant. Use the context provided below to inform your responses. "
            "Always prioritize information from the context layers when relevant to the user's question.\n\n"
            "Sources are labeled with publication dates. This domain evolves rapidly — when sources "
            "conflict, prefer the more recent one. If you rely on information that may be outdated "
            "given its date, briefly note that.\n\n"
            "{context_layers}\n\n"
            "{rag_context}"
        ),
    },
    # -----------------------------------------------------------------------
    # Rolling Summary Compression — KIN-392
    # -----------------------------------------------------------------------
    "conversation-summary-v1": {
        "summarize_new": (
            "Summarize the conversation below into a concise paragraph (200–400 words). "
            "Focus on: decisions made, topics discussed, key facts established, and the user's goals. "
            "This summary will replace older messages as context for future turns in the same conversation. "
            "Be specific and preserve important details. "
            "Return only the summary text — no preamble, no heading."
        ),
        "summarize_incremental": (
            "You have a running summary of an ongoing conversation, plus new messages that have since occurred. "
            "Update the summary to incorporate the new messages. "
            "The updated summary should be concise (200–400 words) and cover the full conversation arc. "
            "Focus on: decisions made, topics discussed, key facts, and the user's goals. "
            "Return only the updated summary text — no preamble, no heading."
        ),
    },
    # -----------------------------------------------------------------------
    # Generate Instructions from KB — KIN-366
    # -----------------------------------------------------------------------
    "generate-instructions-v1": {
        "system_prompt_generate": (
            "You are building a system prompt for an AI agent that thinks and reasons "
            "like the person whose writing is provided below. Analyze the corpus for: "
            "(1) thinking style, (2) communication patterns, (3) core principles, "
            "(4) areas of expertise, (5) distinctive perspective. "
            "Generate a system prompt (300-500 tokens) written as instructions to an LLM. "
            "The prompt should begin with 'You are [name]...' and instruct the model to "
            "adopt this person's reasoning style, principles, and communication patterns. "
            "Do not simply summarize the documents. Synthesize across all provided content."
        ),
    },
}


def get_prompt(prompt_id: str, field: str) -> str:
    """
    Look up a prompt template by ID and field.

    Args:
        prompt_id: Versioned prompt identifier (e.g. "generate-user-profile-v1").
        field: Sub-prompt key within the prompt group (e.g. "name_extract").

    Returns:
        The prompt text.

    Raises:
        KeyError: Unknown prompt_id or field.
    """
    if prompt_id not in PROMPTS:
        raise KeyError(f"Unknown prompt_id: {prompt_id!r}")
    group = PROMPTS[prompt_id]
    if field not in group:
        raise KeyError(f"Unknown field {field!r} for prompt {prompt_id!r}")
    return group[field]
