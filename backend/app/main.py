"""FastAPI entrypoint for AgentOps Copilot API.

**Architecture overview**
- ``core/config.py``       — pydantic-settings config loader (fails fast on
                             missing required env vars)
- ``db/supabase_client.py``— singleton Supabase client; startup probe runs
                             in the lifespan hook below
- ``api/routers/``         — one file per logical group; each exposes an
                             ``APIRouter`` registered here

**Running locally**
    uvicorn app.main:app --reload

**Swagger UI** (local only)
    http://localhost:8000/docs
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    activity,
    approvals,
    auth,
    dashboard,
    digests,
    health,
    me,
    notifications,
    oauth,
    tasks,
)
from app.db.supabase_client import probe_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("AgentOps Copilot API starting up.")
    probe_connection()
    from app.agents.runner import checkpointer_lifespan
    from app.jobs.digest_job import start_scheduler, stop_scheduler

    scheduler = start_scheduler()
    async with checkpointer_lifespan():
        logger.info("Startup complete - server ready.")
        yield
    stop_scheduler(scheduler)
    logger.info("AgentOps Copilot API shutting down.")


app = FastAPI(
    title="AgentOps Copilot API",
    description=("Backend for AgentOps Copilot — AI-powered mobile DevOps companion."),
    version="0.1.0",
    lifespan=lifespan,
    # Disable docs in production via env var in a future day.
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(activity.router)
app.include_router(tasks.router)
app.include_router(oauth.router)
app.include_router(approvals.router)
app.include_router(digests.router)
app.include_router(notifications.router)
app.include_router(dashboard.router)
