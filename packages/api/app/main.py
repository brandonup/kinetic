"""
Kinetic FastAPI application entry point.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import add_exception_handlers
from app.api.routes import (
    companies,
    projects,
    profile,
    admin_models,
    admin_users,
    conversations,
    agents,
    frameworks,
)

app = FastAPI(title="Kinetic API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

add_exception_handlers(app)

app.include_router(profile.router)
app.include_router(companies.router)
app.include_router(projects.router)
app.include_router(admin_models.router)
app.include_router(admin_users.router)
app.include_router(conversations.router)
app.include_router(agents.router)
app.include_router(frameworks.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
