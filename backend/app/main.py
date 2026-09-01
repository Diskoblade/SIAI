"""FastAPI application entrypoint.

Wires configuration, CORS, database initialization, department seeding, and
all route modules together.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database import SessionLocal, init_db
from app.routes import (
    admin,
    approval_notes,
    auth,
    conversations,
    departments,
    documents,
    ide,
    memories,
    onlyoffice,
    rag,
)
from app.seed import seed_departments
from app.services.approval_note_type_service import seed_default_types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed default departments on startup.
    init_db()
    db = SessionLocal()
    try:
        created = seed_departments(db)
        if created:
            logger.info("Seeded %d default department(s).", created)
        note_types = seed_default_types(db)
        if note_types:
            logger.info("Seeded %d default Approval Note type(s).", note_types)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Secure AI-powered departmental knowledge access.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow only the configured frontend origin(s), never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(departments.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(memories.router)
app.include_router(conversations.router)
app.include_router(rag.router)
app.include_router(ide.router)
app.include_router(approval_notes.router)
app.include_router(onlyoffice.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
