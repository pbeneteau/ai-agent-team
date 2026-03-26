# AI Agent Team Orchestrator

You write the brief. We deliver the work. You review the diff.

An AI-powered autonomous agency for knowledge work and code. Users write a brief, a cross-functional team of specialized AI agents collaborates to produce the deliverable, and the user reviews and iterates on the output through version-controlled diffs.

## How It Works

1. **Brief** — Describe what you need (a landing page, an API spec, a research report)
2. **Execute** — A team of AI agents is assembled, plans a DAG, and produces the artifact
3. **Review** — You get versioned output with diffs, leave comments, request iterations

## Architecture

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| Object Storage | MinIO (S3-compatible) |
| AI | Anthropic Claude (Sonnet / Opus / Haiku) |
| Frontend | Next.js 15+, TypeScript, Tailwind CSS v4, shadcn/ui |

## Getting Started

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Node.js 20+ (for frontend, Sprint 8+)

### 1. Clone and configure

```bash
git clone git@github.com:pbeneteau/ai-agent-team.git
cd ai-agent-team
cp backend/.env.example backend/.env
# Edit backend/.env — add your ANTHROPIC_API_KEY
```

### 2. Start infrastructure

```bash
docker-compose up postgres redis minio -d
```

### 3. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run workers (when available)

```bash
celery -A app.core.celery_app worker --concurrency=1 --loglevel=info
celery -A app.core.celery_app beat --loglevel=info
```

### 5. Or run everything with Docker

```bash
docker-compose up
```

## Project Structure

```
backend/
├── app/
│   ├── main.py            # FastAPI app, CORS, error handlers
│   ├── config/
│   │   └── settings.py    # Pydantic Settings (env-driven)
│   ├── core/
│   │   └── database.py    # Async SQLAlchemy engine + session
│   ├── models/            # One file per SQLAlchemy model
│   ├── api/routes/        # One file per API domain
│   ├── agents/            # AI agent engine
│   └── tools/             # Agent tool implementations
├── alembic/               # Database migrations
├── tests/
├── Dockerfile
└── requirements.txt
docs/TDD/                  # Technical Design Documents (6 files)
docker-compose.yml         # Full stack: postgres, redis, minio, backend, worker, beat, frontend
```

## Documentation

The `docs/TDD/` directory contains the full technical design:

| Document | Contents |
|---|---|
| `01_PRD_AND_WORKFLOWS.md` | Product requirements, user journeys, edge cases |
| `02_BACKEND_ARCHITECTURE_TDD.md` | Database schema, S3 layout, Celery tasks, Docker services |
| `03_AI_AGENT_ENGINE_TDD.md` | DAG templates, prompt architecture, tools, reflection |
| `04_API_AND_INTEGRATIONS_TDD.md` | 44 REST endpoints, GitHub/GitLab webhooks, MCP |
| `05_FRONTEND_UX_TDD.md` | Routes, design tokens, state management, UX flows |
| `06_IMPLEMENTATION_ROADMAP.md` | 49 tickets across 12 sprints |

## License

Private — all rights reserved.
