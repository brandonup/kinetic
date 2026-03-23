"""
Kinetic API — FastAPI application entry point.

Wires together: CORS, exception handlers, and routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import add_exception_handlers
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
from app.middleware.log_scrub import LogScrubMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    description="Context-rich AI workspace API",
    version="0.1.0",
)

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
