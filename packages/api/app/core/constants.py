"""Shared constants used across route modules."""

# Document statuses that indicate active ingestion — deletion must be blocked.
ACTIVE_INGESTION_STATUSES: frozenset[str] = frozenset({
    "extracting",
    "chunking",
    "embedding",
})
