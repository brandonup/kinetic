"""Document date validation and plausibility clamping.

Used by ingestion paths that populate `knowledge_base_documents.document_date`.
Implements the both-tail clamp described in
`docs/plans/2026-05-21-recency-aware-retrieval-design.md` § Component A and
§ Edge Cases: future dates beyond today+1d and pre-2015 dates are treated as
invalid (poller/bulk paths coerce to NULL; the user-facing upload endpoint
rejects with 422 so the caller learns of the bad input).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

# Floor — anything older is treated as a parse-failure sentinel (e.g.
# `datetime.min` from `substack.py:_parse_date`) or an obvious typo.
MIN_PLAUSIBLE_DATE: date = date(2015, 1, 1)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def is_plausible_document_date(value: date) -> bool:
    """True when ``value`` lies inside [MIN_PLAUSIBLE_DATE, today+1d UTC]."""
    if value < MIN_PLAUSIBLE_DATE:
        return False
    if value > _today_utc() + timedelta(days=1):
        return False
    return True


def coerce_optional_date(value: Optional[date]) -> Optional[date]:
    """Return ``value`` if plausible, else ``None``. Never raises."""
    if value is None:
        return None
    try:
        return value if is_plausible_document_date(value) else None
    except Exception:
        return None


def datetime_to_document_date(value: Optional[datetime]) -> Optional[date]:
    """Convert a UTC-ish ``datetime`` to a plausible ``date``.

    Anything outside the plausibility window (including ``datetime.min``,
    which ``substack.py:_parse_date`` returns on failure) maps to ``None``.
    """
    if value is None:
        return None
    try:
        return coerce_optional_date(value.date())
    except Exception:
        return None
