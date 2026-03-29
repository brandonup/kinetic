"""
LLM judge for Linked Upload extraction eval (KIN-328).

Two judge functions:
  judge_name()        — checks name precision (exact match after normalisation)
  judge_relevance()   — scores bio/description/instructions on 1-3 rubric

Relevance rubric (1-3):
  3 = GOOD: covers the right content, accurate, appropriately detailed
  2 = ACCEPTABLE: mostly right but missing some key context or slightly imprecise
  1 = POOR: significantly wrong, missing main content, or hallucinated information
"""

import json
import re
import sys

RELEVANCE_JUDGE_PROMPT = """You are evaluating an AI-extracted field from a document.

**Surface:** {surface}
**Field:** {field_name}
**Document (truncated):**
{document_snippet}

**Extraction output:**
"{extracted}"

**Score this 1, 2, or 3:**
- 3 = GOOD: Accurate, covers the right content at the right detail level for the field.
  Would be useful to someone reading this summary without the original document.
- 2 = ACCEPTABLE: Mostly correct but missing some relevant context, slightly imprecise,
  or over-summarized in ways that lose important detail.
- 1 = POOR: Significantly wrong, missing the main point, hallucinated content not in
  the document, or so generic as to be useless.

**For `instructions` (agent surface):** Score 3 if it captures at least 3 of the following:
thinking style, communication patterns, core principles, areas of expertise, distinctive perspective.
Score 2 if 2 are captured. Score 1 if 0-1.

Respond with ONLY: {{"score": <1|2|3>, "reason": "<one sentence>"}}"""


def normalise_name(name: str | None) -> str | None:
    if name is None:
        return None
    return name.strip().lower()


def judge_name(extracted_name: str | None, expected_name: str | None) -> dict:
    """
    Name precision check — exact match after normalisation.

    Returns: {"precise": bool, "extracted": str|None, "expected": str|None}
    """
    norm_extracted = normalise_name(extracted_name)
    norm_expected = normalise_name(expected_name)

    if norm_expected is None:
        # Edge case: no expected name — check that extraction returns null/None
        precise = extracted_name is None or extracted_name.lower() in ("null", "none", "")
        return {"precise": precise, "extracted": extracted_name, "expected": None, "note": "edge: expected null"}

    precise = norm_extracted == norm_expected
    return {"precise": precise, "extracted": extracted_name, "expected": expected_name}


def judge_relevance(
    extracted_text: str | None,
    document_text: str,
    surface: str,
    field_name: str,
    api_key: str,
    model: str = "gpt-4o",
) -> dict:
    """
    Score bio/description/instructions relevance using LLM judge.

    Returns: {"score": int, "reason": str}
    """
    if not extracted_text or extracted_text.strip() == "":
        return {"score": 1, "reason": "extracted field is empty or null"}

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent / "packages" / "api"))
    from app.services.llm_client import call_llm

    prompt = RELEVANCE_JUDGE_PROMPT.format(
        surface=surface,
        field_name=field_name,
        document_snippet=document_text[:3000],
        extracted=extracted_text[:800],
    )
    raw = call_llm(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        api_key=api_key,
        max_tokens=150,
        timeout=20,
    ).strip()

    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    data = json.loads(cleaned)
    return {"score": int(data["score"]), "reason": data.get("reason", "")}
