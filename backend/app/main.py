import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.routes import agents, artifacts, documents, git_providers, labels, mcp, projects, task_comments, task_relations, teams, usage
from app.core.agent_factory import get_agent_factory
from app.core.orchestrator import get_orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting AI Agent Team Orchestrator")
    logger.info(f"Using Claude model: {settings.claude_model}")

    # Ensure associate agent exists on startup
    factory = get_agent_factory()
    associate = factory.get_or_create_associate()
    logger.info(f"Associate agent ready: {associate.name} ({associate.id})")

    orchestrator = get_orchestrator()
    task_recovery = orchestrator.reconcile_interrupted_tasks()
    agent_recovery = factory.reconcile_runtime_state_after_restart()
    if task_recovery["recovered_tasks"] or agent_recovery["updated_agents"]:
        logger.warning(
            "Recovered local runtime state after restart: %s interrupted task(s), %s interrupted node(s), %s agent(s) reconciled.",
            task_recovery["recovered_tasks"],
            task_recovery["recovered_nodes"],
            agent_recovery["updated_agents"],
        )

    yield

    logger.info("Shutting down AI Agent Team Orchestrator")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI Agent Team Orchestrator",
        description="Manage your AI agent team for your startup",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(artifacts.router, prefix="/api")
    app.include_router(task_comments.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(teams.router, prefix="/api")
    app.include_router(task_relations.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(labels.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(usage.router, prefix="/api")
    app.include_router(mcp.router, prefix="/api")
    app.include_router(git_providers.router, prefix="/api")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "ai-agent-team"}

    return app


app = create_app()
