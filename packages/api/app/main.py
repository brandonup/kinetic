"""
Kinetic API — FastAPI application entry point.

Wires together: CORS, exception handlers, routers, and startup tasks.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import add_exception_handlers
from app.services.background import cleanup_stale_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup/shutdown lifecycle.

    Startup: stale job cleanup (KIN-338), scrape source poller (KIN-462).
    Shutdown: graceful scheduler stop.
    """
    # --- Startup ---
    try:
        from app.db.supabase_client import get_supabase
        supabase = get_supabase()
        cleaned = await cleanup_stale_jobs(supabase)
        if cleaned:
            logger.info("Startup: cleaned up %d stale background jobs", cleaned)
    except Exception as exc:
        logger.warning("Startup: stale job cleanup failed (non-fatal): %s", exc)

    # Start APScheduler for scrape source polling (KIN-462)
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        from app.services.scraping.poller import POLL_INTERVAL_MINUTES, poll_scrape_sources

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            poll_scrape_sources,
            trigger=IntervalTrigger(minutes=POLL_INTERVAL_MINUTES),
            id="scrape_source_poller",
            name="Scrape source poller",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Startup: scrape source poller started (every %d min)", POLL_INTERVAL_MINUTES)
    except Exception as exc:
        logger.warning("Startup: scrape source poller failed to start (non-fatal): %s", exc)

    yield

    # --- Shutdown ---
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
            logger.info("Shutdown: scrape source poller stopped")
        except Exception as exc:
            logger.warning("Shutdown: scheduler stop failed (non-fatal): %s", exc)
from app.api.routes.users import router as users_router
from app.api.routes.documents import router as documents_router
from app.api.routes.profile import router as profile_router
from app.api.routes.companies import router as companies_router
from app.api.routes.projects import router as projects_router
from app.api.routes.admin_models import router as admin_models_router
from app.api.routes.admin_users import router as admin_users_router
from app.api.routes.active_memory import router as active_memory_router
from app.api.routes.active_memory import admin_router as active_memory_admin_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.linked_upload import router as linked_upload_router
from app.api.routes.agents import router as agents_router
from app.api.routes.mcp_tokens import router as mcp_tokens_router
from app.api.routes.mcp import router as mcp_router
from app.api.routes.admin_rag_debug import router as admin_rag_debug_router
from app.api.routes.admin_request_trace import router as admin_request_trace_router
from app.api.routes.admin_prompt_debug import router as admin_prompt_debug_router
from app.api.routes.admin_backfill import router as admin_backfill_router
from app.api.routes.admin_mcp_logs import router as admin_mcp_logs_router
from app.api.routes.kb_management import router as kb_management_router
from app.api.routes.generation import router as generation_router
from app.api.routes.scrape_sources import router as scrape_sources_router
from app.middleware.log_scrub import LogScrubMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    description="Context-rich AI workspace API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway / load balancer probes."""
    return {"status": "ok"}

# Log scrub must be added before CORS so it fires on every request
app.add_middleware(LogScrubMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

add_exception_handlers(app)
app.include_router(users_router)
app.include_router(documents_router)
app.include_router(profile_router)
app.include_router(companies_router)
app.include_router(projects_router)
app.include_router(admin_models_router)
app.include_router(admin_users_router)
app.include_router(active_memory_router)
app.include_router(active_memory_admin_router)
app.include_router(conversations_router)
app.include_router(linked_upload_router)
app.include_router(agents_router)
app.include_router(mcp_tokens_router)
app.include_router(mcp_router)
app.include_router(admin_rag_debug_router)
app.include_router(admin_request_trace_router)
app.include_router(admin_prompt_debug_router)
app.include_router(admin_backfill_router)
app.include_router(admin_mcp_logs_router)
app.include_router(kb_management_router)
app.include_router(generation_router)
app.include_router(scrape_sources_router)
