# AI Agent Team — Code Factory

> *You write the brief. We deliver the code. You review the diff.*

An AI-powered autonomous code factory. Write a brief describing what you need, a cross-functional team of specialized AI agents (leads + workers) collaborates to produce the code, and you review and iterate through version-controlled diffs and GitHub/GitLab PRs.

## How It Works

```
Brief ──> Sufficiency Check ──> DAG Routing ──> Leads Plan ──> [Validate] ──> Workers Execute ──> Leads Review ──> Iterate ──> Approve
```

1. **Write a Smart Brief** — describe the code you need (goal, tech stack, constraints)
2. **Validate** — AI checks if the brief is complete enough to produce quality output
3. **Delegate** — system selects the right DAG template, assembles leads + workers from your roster
4. **Plan** — lead agents analyze the brief and produce a structured delegation plan
5. **Execute** — worker agents implement in parallel, building on the delegation plan
6. **Review** — lead agents grade against template-specific criteria, run code via `code_exec`
7. **Iterate** — leads REVISE with per-specialist feedback, or MINOR_FIX directly
8. **Approve** — agents reflect on the work and accumulate learnings for next time

## Key Features

- **Lead-guided execution** — leads plan and review, workers execute. APPROVE / MINOR_FIX / REVISE decisions with per-specialist feedback
- **13 code-focused DAG templates** — `full_feature`, `backend_feature`, `frontend_feature`, `bug_fix`, `refactor`, `security_fix`, `performance`, `infra_devops`, `mobile_feature`, `data_feature`, `api_integration`, `architecture`, `design_system`
- **Template-specific grading** — review leads grade against numbered PASS/FAIL criteria per template, with anti-rationalization prompts
- **Code execution in review** — `code_exec` tool lets review leads run tests, lint, and build in a sandboxed temp dir
- **Delegation validation** — optional validation wave catches vague delegation plans before workers waste tokens (on complex templates)
- **Context management** — mid-loop Haiku summarization at 60K tokens, upstream truncation (47/53 middle-out), memory compaction
- **Persistent agent roster** — agents accumulate skills and learnings across executions, improving over time
- **GitHub/GitLab integration** — code artifacts auto-push to PR branches, webhook-driven iteration from PR comments
- **Execution telemetry** — structured JSON metrics for tool iterations, token peaks, review decisions, compaction frequency
- **Cost controls** — per-artifact and monthly budget ceilings with hard circuit breakers
- **MCP support** — connect external tool servers for agent use during execution
- **All constants tunable** — 12 agent parameters configurable via env vars without code changes

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

Open [http://localhost:3005](http://localhost:3005). Complete onboarding to generate your agent roster.

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
│   │   │   ├── orchestrator.py        # Lead-guided DAG orchestrator
│   │   │   ├── telemetry.py          # Structured JSON execution metrics
│   │   │   ├── router.py             # Haiku-powered DAG routing + agent assembly
│   │   │   ├── prompt_builder.py      # 9-position prompt + review criteria
│   │   │   ├── memory.py             # Agent skill/learning loader + compaction
│   │   │   ├── upstream.py           # Cross-wave context builder
│   │   │   ├── sufficiency.py        # Brief validation (Sonnet)
│   │   │   ├── reflection.py         # Post-execution self-improvement
│   │   │   ├── learning.py           # Initial skill acquisition
│   │   │   ├── briefing.py           # Project context distribution
│   │   │   ├── readiness.py          # Heuristic readiness scoring
│   │   │   ├── document_processor.py  # PDF/DOCX/text extraction + chunking
│   │   │   └── dag_templates/        # 13 lead-guided code templates
│   │   ├── api/
│   │   │   ├── routes/            # 11 route files, 49 endpoints
│   │   │   ├── schemas/           # 8 files: Pydantic request/response models
│   │   │   └── websocket_manager.py   # Real-time event broadcasting
│   │   ├── config/settings.py     # Pydantic Settings (env-driven, 12 tunable agent params)
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
│   │   └── tools/                 # 8 agent tools (incl. code_exec for review)
│   ├── alembic/versions/          # 10 migrations (FK-dependency order)
│   ├── scripts/                   # analyze_telemetry.py (tuning report from logs)
│   └── tests/
│       ├── e2e/                   # End-to-end tests
│       └── *.py                   # 760 unit + integration tests
├── frontend/
│   ├── AGENTS.md                  # Next.js agent rules (read before writing frontend code)
│   ├── CLAUDE.md                  # Imports AGENTS.md rules for Claude
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
│   ├── ARCHITECTURE.md            # System-level architecture overview
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
              DAG Router (Haiku) ──> selects template + maps leads/workers
                     │
                     ▼
            ┌── Planning ────────────────┐
            │  Lead A ─┐                 │  Leads analyze brief,
            │  Lead B ─┘ asyncio.gather  │  produce delegation plan
            └────────────┬───────────────┘
                         │
                         ▼ (optional, complex templates)
            ┌── Validation ──────────────┐
            │  Lead validates delegation │  APPROVED → continue
            │  plan specificity          │  REVISE → re-plan (1x)
            └────────────┬───────────────┘
                         │
          ┌──────────────▼──────────────────────────┐
          │  EXECUTION + REVIEW LOOP (max N iters)  │
          │                                         │
          │  ┌── Execution ──────────────────┐      │
          │  │  Worker A ─┐                  │      │
          │  │  Worker B ─┘ asyncio.gather   │      │
          │  └────────────┬──────────────────┘      │
          │               ▼                         │
          │  ┌── Review ─────────────────────┐      │
          │  │  Lead grades via criteria +   │      │
          │  │  code_exec (run tests/lint)   │      │
          │  │  → APPROVE / MINOR_FIX / REVISE      │
          │  └────────────┬──────────────────┘      │
          │               │ REVISE → loop back      │
          └───────────────┼─────────────────────────┘
                          │ APPROVE or MINOR_FIX
                          ▼
              Upload to S3 ──> Create ArtifactVersion
                          │
                          ▼
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

760 backend tests + 46 Playwright E2E tests. GitHub Actions CI runs on every push.

### Performance Baseline

All key endpoints meet their latency targets (p95, mocked where applicable):

| Metric | p95 (ms) | Target | Status |
|--------|----------|--------|--------|
| GET /api/roster | 0.91 | <100ms | PASS |
| GET /api/artifacts/{id} | 0.74 | <100ms | PASS |
| GET /api/artifacts/{id}/status | 0.97 | <50ms | PASS |
| File proxy (50KB) | 0.93 | <200ms | PASS |
| Sufficiency check (mocked LLM) | 1.46 | <4000ms | PASS |
| Delegate preview (mocked router) | 1.32 | <2000ms | PASS |

## Documentation

| Document | Contents |
|---|---|
| `docs/ARCHITECTURE.md` | System-level architecture overview, module map, ADRs, deployment pipeline |
| `docs/VISION_2.0.md` | Product vision and strategic context |
| `docs/TDD/01_PRD_AND_WORKFLOWS.md` | User personas, 6 journeys, state machine, edge cases |
| `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md` | 12 tables, S3 layout, Celery tasks, circuit breakers |
| `docs/TDD/03_AI_AGENT_ENGINE_TDD.md` | Prompts, DAG templates, memory, 8 tools, reflection |
| `docs/TDD/04_API_AND_INTEGRATIONS_TDD.md` | All 49 endpoint specs with request/response schemas |
| `docs/TDD/05_FRONTEND_UX_TDD.md` | Design tokens, routes, state management, UX specs |
| `docs/TDD/06_IMPLEMENTATION_ROADMAP.md` | 74 tickets across 17 sprints |

## License

Private — all rights reserved.