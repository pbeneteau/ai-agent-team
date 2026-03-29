from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.core.errors import ApiError, api_error_handler
from app.core.s3_workspace import ensure_bucket


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: ensure S3 bucket exists
    ensure_bucket()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="AI Agent Team Orchestrator",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.exception_handler(ApiError)(api_error_handler)

# ---------------------------------------------------------------------------
# Register routers (Sprint 6)
# ---------------------------------------------------------------------------

from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.roster import router as roster_router
from app.api.routes.projects import router as projects_router
from app.api.routes.artifacts import router as artifacts_router

app.include_router(onboarding_router)
app.include_router(roster_router)
app.include_router(projects_router)
app.include_router(artifacts_router)

# ---------------------------------------------------------------------------
# Register routers (Sprint 7)
# ---------------------------------------------------------------------------

from app.api.routes.git_providers import router as git_providers_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.mcp import router as mcp_router
from app.api.routes.usage import router as usage_router
from app.api.routes.health import router as health_router
from app.api.routes.workspace import router as workspace_router

app.include_router(git_providers_router)
app.include_router(webhooks_router)
app.include_router(mcp_router)
app.include_router(usage_router)
app.include_router(health_router)
app.include_router(workspace_router)


# ---------------------------------------------------------------------------
# WebSocket endpoint (Sprint 7 — Ticket 7.5)
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket connection endpoint for real-time event broadcasting.

    Ref: TDD-05 Section 6.
    """
    from app.api.websocket_manager import ws_manager

    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive — wait for client messages
            # (clients may send pings; we just read and discard)
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)
