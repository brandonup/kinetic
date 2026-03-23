"""
Kinetic API — FastAPI application entry point.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import KineticError, kinetic_error_handler
from app.api.routes.agents import router as agents_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.generation import router as generation_router

app = FastAPI(
    title="Kinetic API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

app.add_exception_handler(KineticError, kinetic_error_handler)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(agents_router)
app.include_router(conversations_router)
app.include_router(generation_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
