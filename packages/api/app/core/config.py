"""
Application configuration and settings for Kinetic.

LLM keys are BYOK — they come from the user's encrypted profile
(user_api_keys table). Embedding uses a platform-owned Gemini key
(GEMINI_API_KEY env var) so users don't need a configured key for
document upload or RAG retrieval. Enrichment uses the user's BYOK
Anthropic key. Chat generation uses the user's BYOK key for their
chosen model provider.
"""

import os
from pathlib import Path
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings

# Resolve backend directory and .env path relative to this file, not CWD
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Kinetic"
    DEBUG: bool = False
    ADMIN_PORTAL_URL: str = "http://localhost:3000"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = "http://localhost:3000"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS_ORIGINS from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Environment
    ENVIRONMENT: str = "development"  # development, staging, production

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str
    SUPABASE_STORAGE_BUCKET: str = "uploads"

    # Encryption — AES-256-GCM key for user API key storage
    # Must be 32 bytes base64-encoded. Never expose in logs or responses.
    API_KEY_ENCRYPTION_KEY: str

    # Platform embedding — Gemini Embedding 001 via server-side key (KIN-467, KIN-476)
    # 3072 is gemini-embedding-001's native dim. The embedder only passes
    # `output_dimensionality` to the SDK when this differs from 3072 (KIN-476).
    GEMINI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMS: int = 3072

    # Pipeline models (not user-facing — users pick generation model per query)
    FRAMEWORK_RERANKER_MODEL: str = "claude-haiku-3-5"
    CONVERSATION_COMPRESSION_MODEL: str = "claude-haiku-3-5"

    # Feature flags
    LLM_ENABLED: bool = True
    RAG_ENABLED: bool = True
    ENRICHMENT_ENABLED: bool = True  # Document-level AI summary at ingestion time
    SEMANTIC_CHUNKING_ENABLED: bool = False  # KIN-470: topic-based chunking via embeddings

    # Semantic chunking parameters (KIN-470, word-count proxy per KIN-467)
    SEMANTIC_WINDOW_WORDS: int = 112       # sliding window size for topic detection (~150 tokens)
    SEMANTIC_WINDOW_STRIDE: int = 3        # slide every N sentences (reduces embedding cost)
    SEMANTIC_BREAKPOINT_THRESHOLD: float = 1.5  # stddev multiplier for breakpoint detection
    SEMANTIC_MIN_CHUNK_WORDS: int = 150    # merge smaller chunks (~200 tokens)
    SEMANTIC_MAX_CHUNK_WORDS: int = 750    # split larger chunks (~1000 tokens)

    # Ingestion job controls
    INGESTION_TOKEN_LIMIT: int = 1_000_000  # max tokens per document (mirrors PRD)
    MAX_INGESTION_RETRIES: int = 3
    INGESTION_RETRY_DELAYS: List[int] = [60, 300, 900]  # seconds: 1m, 5m, 15m

    # Embeddings
    EMBEDDING_BATCH_SIZE: int = 100
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_RETRY_MIN_WAIT: int = 2  # seconds
    EMBEDDING_RETRY_MAX_WAIT: int = 10  # seconds
    EMBEDDING_SLEEP_BETWEEN_BATCHES: float = 0.5

    # RAG retrieval parameters
    VECTOR_TOP_K: int = 20              # candidates from vector search
    MMR_TOP_K: int = 8                  # candidates after MMR selection
    MMR_LAMBDA: float = 0.6             # relevance/diversity tradeoff (higher = favour relevance)
    SIMILARITY_THRESHOLD: float = 0.3   # minimum cosine similarity for chunk injection
    RAG_MAX_TOKENS_PERCENT: float = 0.15  # token budget as fraction of model context window
    RAG_MAX_TOKENS_FLOOR: int = 2048    # minimum token budget regardless of context window

    # MCP rate limiting (per-user daily cap, admin-configurable)
    MCP_RATE_LIMIT_DEFAULT: int = 1000  # requests per day

    # Local dev auth bypass (never True in production)
    LOCAL_DEV_AUTH_BYPASS: bool = False

    model_config = {
        "env_file": str(ENV_FILE_PATH),
        "case_sensitive": True,
        "extra": "ignore",  # Tolerate stale env vars (e.g., removed PLATFORM_*_KEY)
    }


def validate_settings(s: Settings) -> None:
    """Validate critical settings on startup."""
    required_fields = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_JWT_SECRET",
        "API_KEY_ENCRYPTION_KEY",
        "GEMINI_API_KEY",
    ]

    missing = []
    for field in required_fields:
        if not getattr(s, field, None):
            missing.append(field)

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Please check backend/.env (resolved relative to the backend directory)."
        )

    env = getattr(s, "ENVIRONMENT", "development").lower()
    if env == "production":
        warnings = []
        if "localhost" in (s.ADMIN_PORTAL_URL or ""):
            warnings.append("ADMIN_PORTAL_URL should not point to localhost in production")
        if s.CORS_ORIGINS and any(
            origin.startswith("http://localhost") for origin in s.CORS_ORIGINS
        ):
            warnings.append("CORS_ORIGINS contains localhost in production")
        if warnings:
            raise ValueError(f"Production configuration issue(s): {'; '.join(warnings)}")


# Initialize settings
try:
    settings = Settings()  # type: ignore[call-arg]
except Exception:
    raise

# Only validate in non-test environments
if os.getenv("PYTEST_CURRENT_TEST") is None:
    validate_settings(settings)


def is_reasoning_model(model_name: str) -> bool:
    """
    Check if a model requires reasoning-specific parameters.

    Reasoning models:
    - Require max_completion_tokens instead of max_tokens
    - Only support temperature=1 (default), cannot set custom temperature

    Args:
        model_name: The model name string (e.g., "o1-preview", "gemini-2.0-flash-thinking")

    Returns:
        True if the model is a reasoning model, False otherwise
    """
    if not model_name:
        return False
    model_lower = model_name.lower()
    return any(pattern in model_lower for pattern in ["o1", "o3", "o4", "gpt-5", "thinking"])
