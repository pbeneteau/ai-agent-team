# AI Agent Team Orchestrator

> *You write the brief. We deliver the work. You review the diff.*

An AI-powered autonomous agency for knowledge work and code. Describe what you need in a structured brief, a cross-functional team of specialized AI agents collaborates to produce the deliverable, and you review and iterate on the output through version-controlled diffs.

## How It Works

```
Brief ──> Sufficiency Check ──> DAG Routing ──> Parallel Agent Execution ──> Review ──> Iterate ──> Approve
```

1. **Write a Smart Brief** — describe the deliverable (goal, audience, context, constraints)
2. **Validate** — AI checks if the brief is complete enough to produce quality output
3. **Delegate** — system selects the right DAG template, assembles a team from your roster, estimates cost
4. **Execute** — agents work in parallel waves, each building on the output of the previous wave
5. **Review** — see the output, sources, assumptions, and cost. View diffs between versions.
6. **Iterate** — highlight text, leave a comment, agents rewrite just that section
7. **Approve** — agents reflect on the work and accumulate learnings for next time

## Key Features

- **Multi-agent collaboration** — specialized agents (product, design, engineering, QA) work cross-functionally via DAG-based execution
- **5 DAG templates** — `code_feature`, `content_research`, `simple_prose`, `code_bugfix`, `multi_research`
- **Persistent agent roster** — agents accumulate skills and learnings across executions, improving over time
- **Artifact versioning** — immutable versions with prose diffs (in-app) and code diffs (GitHub/GitLab PRs)
- **Contextual iteration** — highlight text, leave a comment, agents rewrite only what you flagged
- **GitHub/GitLab integration** — code artifacts auto-push to PR branches, webhook-driven iteration from PR comments
- **Cost controls** — per-artifact and monthly budget ceilings with hard circuit breakers
- **MCP support** — connect external tool servers for agent use during execution

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| Object Storage | MinIO (S3-compatible) |
| AI | Anthropic Claude API (Sonnet, Haiku, Opus) |
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| State | Zustand (UI), TanStack Query (server) |
| Infra | Docker Compose |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+ with pnpm
- Anthropic API key

### 1. Clone and configure

```bash
git clone git@github.com:pbeneteau/ai-agent-team.git
cd ai-agent-team
cp backend/.env.example backend/.env
# Edit backend/.env — add your ANTHROPIC_API_KEY
```

### 2. Start infrastructure

```bash
docker compose up postgres redis minio -d
```

### 3. Run the backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In separate terminals:

```bash
celery -A app.core.celery_app worker --concurrency=1 --loglevel=info
celery -A app.core.celery_app beat --loglevel=info
```

### 4. Run the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000). Complete onboarding to generate your agent roster.

### 5. Or run everything via Docker

```bash
docker compose up
```

## Project Structure

```
ai-agent-team/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, lifespan, error handlers
│   │   ├── agents/                # AI engine
│   │   │   ├── anthropic_runner.py    # Core agent execution loop
│   │   │   ├── orchestrator.py        # DAG orchestrator (execute_artifact_dag)
│   │   │   ├── router.py             # Haiku-powered DAG routing + agent assembly
│   │   │   ├── prompt_builder.py      # 9-position prompt architecture
│   │   │   ├── memory.py             # Agent skill/learning loader + compaction
│   │   │   ├── upstream.py           # Cross-wave context builder
│   │   │   ├── sufficiency.py        # Brief validation (Sonnet)
│   │   │   ├── reflection.py         # Post-execution self-improvement
│   │   │   ├── learning.py           # Initial skill acquisition
│   │   │   ├── briefing.py           # Project context distribution
│   │   │   ├── readiness.py          # Heuristic readiness scoring
│   │   │   ├── document_processor.py  # PDF/DOCX/text extraction + chunking
│   │   │   └── dag_templates/        # 5 MVP execution templates
│   │   ├── api/
│   │   │   ├── routes/            # 10 route files, 44 endpoints
│   │   │   ├── schemas/           # Pydantic request/response models
│   │   │   └── websocket_manager.py   # Real-time event broadcasting
│   │   ├── config/settings.py     # Pydantic Settings (env-driven)
│   │   ├── core/                  # Infrastructure services
│   │   │   ├── database.py            # Async SQLAlchemy engine + sessions
│   │   │   ├── celery_app.py          # Celery + Redis configuration
│   │   │   ├── s3_workspace.py        # S3/MinIO file operations
│   │   │   ├── cost.py                # Pricing table + budget enforcement
│   │   │   ├── git_push.py            # Clone → branch → commit → push → PR
│   │   │   ├── git_providers/         # GitHub + GitLab API clients
│   │   │   ├── mcp_client.py          # MCP protocol client
│   │   │   ├── encryption.py          # PAT/auth config encryption
│   │   │   ├── pagination.py          # Cursor-based pagination
│   │   │   ├── errors.py             # Standard error envelope
│   │   │   ├── reaper.py             # Orphaned wave cleanup
│   │   │   └── billing.py            # Monthly budget reset
│   │   ├── models/                # 12 SQLAlchemy models + enums
│   │   └── tools/                 # 7 agent tools
│   ├── alembic/versions/          # 8 migrations (FK-dependency order)
│   └── tests/
│       ├── e2e/                   # 78 end-to-end tests
│       └── *.py                   # Unit + integration tests
├── frontend/
│   ├── app/                       # Next.js App Router
│   │   ├── (app)/                     # Main app (projects, roster, settings)
│   │   │   ├── projects/[projectId]/      # Project detail, brief, documents
│   │   │   │   └── artifacts/[artifactId]/ # Heartbeat + review UI
│   │   │   ├── roster/[agentId]/          # Agent detail + skills
│   │   │   └── settings/{git,mcp,usage}/  # Integration settings
│   │   └── (onboarding)/             # Onboarding wizard
│   ├── components/                # Shared UI (sidebar, top bar, shadcn/ui)
│   ├── features/                  # Feature modules
│   │   ├── artifacts/                 # Smart Brief, heartbeat, review, diff viewer
│   │   ├── comments/                  # Contextual commenting (text selection + floating toolbar)
│   │   ├── onboarding/               # Multi-step onboarding form
│   │   ├── projects/                  # Brief editor, document manager
│   │   └── roster/                    # Agent cards, detail tabs, research dialog
│   └── lib/
│       ├── api/                   # Typed API client (all 44 endpoints)
│       ├── hooks/                 # TanStack Query hooks + WebSocket
│       ├── stores/                # Zustand (UI state, text selection)
│       └── types/api.ts           # TypeScript API types
├── docs/
│   ├── VISION_2.0.md              # Product vision
│   └── TDD/                      # 6 Technical Design Documents
└── docker-compose.yml             # 7 services: postgres, redis, minio, backend, worker, beat, frontend
```

## Architecture

### Database (12 tables)

```
workspaces
 ├── agents ──────────────── agent_skills
 ├── projects
 │    ├── artifacts
 │    │    ├── artifact_versions ─── contextual_comments
 │    │    └── execution_waves
 │    └── documents ──────── document_chunks (pgvector)
 ├── git_provider_connections
 └── mcp_connections
```

### Artifact State Machine

```
             ┌─────────┐
             │ drafting │◄──────── iterate (contextual comment)
             └────┬────┘                    │
                  │ execution completes     │
                  ▼                         │
           ┌───────────┐                    │
           │ in_review  │───────────────────┘
           └─────┬─────┘
                 │ approve
                 ▼
           ┌───────────┐
           │  approved  │
           └───────────┘

  (cancel from drafting or in_review → cancelled)
```

### Execution Pipeline

```
Smart Brief ──> Sufficiency Check (Sonnet)
                     │
                     ▼
              DAG Router (Haiku) ──> selects template + maps agents
                     │
                     ▼
            ┌── Wave 1 ──────────────────┐
            │  Slot A ─┐                 │
            │  Slot B ─┤ asyncio.gather  │
            │  Slot C ─┘                 │
            └────────────┬───────────────┘
                         │ upstream context
                         ▼
            ┌── Wave 2 ──────────────────┐
            │  Slot D (depends on A, B)  │
            └────────────┬───────────────┘
                         │
                         ▼
              Upload to S3 ──> Create ArtifactVersion
                         │
                         ▼ (if code artifact)
              Git Push ──> Create PR
```

## API

44 REST endpoints + 1 WebSocket:

| Domain | Endpoints | Key Operations |
|---|---|---|
| Onboarding | 1 | Company setup + roster generation |
| Roster | 15 | Agent CRUD, skills, learning, reflection, research |
| Projects | 7 | CRUD, brief draft/publish, documents |
| Artifacts | 12 | Create, validate, delegate, review, iterate, approve |
| Git Providers | 6 | Connect, test, list repos, configure webhooks |
| Webhooks | 2 | GitHub + GitLab event receivers |
| MCP | 5 | Connect, test, discover tools |
| Usage | 2 | Cost aggregation, budget management |
| WebSocket | 1 | Real-time events (status changes, budget warnings) |
| Health | 1 | Service health check |

## Testing

```bash
# Backend unit + integration tests
cd backend && pytest tests/ -v

# End-to-end tests (requires Docker services)
pytest tests/e2e/ -v

# Frontend type check + build
cd frontend && pnpm build
```

78 E2E tests covering all 6 user journeys and all edge cases from the PRD.

## Documentation

| Document | Contents |
|---|---|
| `docs/VISION_2.0.md` | Product vision and strategic context |
| `docs/TDD/01_PRD_AND_WORKFLOWS.md` | User personas, 6 journeys, state machine, edge cases |
| `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md` | 12 tables, S3 layout, Celery tasks, circuit breakers |
| `docs/TDD/03_AI_AGENT_ENGINE_TDD.md` | Prompts, DAG templates, memory, 7 tools, reflection |
| `docs/TDD/04_API_AND_INTEGRATIONS_TDD.md` | All 44 endpoint specs with request/response schemas |
| `docs/TDD/05_FRONTEND_UX_TDD.md` | Design tokens, routes, state management, UX specs |
| `docs/TDD/06_IMPLEMENTATION_ROADMAP.md` | 49 tickets across 12 sprints |

## License

Private — all rights reserved.
