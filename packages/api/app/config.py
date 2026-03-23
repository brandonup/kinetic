"""
Application settings — loaded once at startup via get_settings().
All env vars read from environment or .env file.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""

    # Platform-owned keys (never BYOK)
    OPENAI_API_KEY: str = ""       # text-embedding-3-large
    ANTHROPIC_API_KEY: str = ""    # Haiku reranker (framework selection)

    # Encryption (API keys at rest)
    API_KEY_ENCRYPTION_KEY: str = ""

    # RAG retrieval (ADR-002)
    VECTOR_TOP_K: int = 20
    MMR_TOP_K: int = 8
    MMR_LAMBDA: float = 0.6
    SIMILARITY_THRESHOLD: float = 0.3

    # Framework selection pipeline (KIN-289)
    FRAMEWORK_SIMILARITY_SHORT_CIRCUIT: float = 0.2   # skip Haiku if no candidate above this
    FRAMEWORK_MIN_RERANK_THRESHOLD: float = 0.3        # pass to Haiku only if ≥1 above this
    FRAMEWORK_EXPERTISE_BOOST: float = 0.05
    FRAMEWORK_TOP_K: int = 5

    # Context stack token budget (ADR-003)
    CONTEXT_WINDOW_BUDGET_RATIO: float = 0.80

    # Conversation compression (ADR-004)
    COMPRESSION_THRESHOLD: int = 20   # user-role message count trigger
    VERBATIM_WINDOW: int = 10          # most-recent messages kept verbatim (5 pairs)

    ENVIRONMENT: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
