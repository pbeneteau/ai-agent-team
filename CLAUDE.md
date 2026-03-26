# AI Agent Team Orchestrator — V2 "Artifact-First"

## What This Is

An AI-powered autonomous agency for knowledge work and code. Users write a brief, a cross-functional team of specialized AI agents collaborates to produce the deliverable, and the user reviews and iterates on the output through version-controlled diffs.

**One-liner:** *You write the brief. We deliver the work. You review the diff.*

## Project Status

V2 redesign — **full clean slate**. All V1 code has been deleted. All 6 Technical Design Documents are complete in `docs/TDD/`. Everything is written from scratch based on the TDD specs. **Follow the roadmap in `docs/TDD/06_IMPLEMENTATION_ROADMAP.md` strictly** — execute tickets in order, one at a time, verify before moving on.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| Object Storage | MinIO (S3-compatible) |
| AI | Anthropic Claude API (Sonnet/Opus/Haiku tiers) |
| Frontend | Next.js 15+ (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| State | Zustand (UI), TanStack Query (server), URL params (navigation) |
| Infrastructure | Docker Compose (postgres, redis, minio, backend, worker, beat, frontend) |

## Architecture — Key Decisions

These are **locked decisions** from the TDD process. Do not revisit or change them without explicit approval.

- **AD-1:** Single-tenant MVP. All tables have `workspace_id` FK. Hardcoded `workspace_id = "1"` in API layer.
- **AD-2:** Celery + Redis for execution (not Temporal).
- **AD-3:** One orchestrator Celery task per execution. `asyncio.gather` for parallel waves within it.
- **AD-4:** Agent skills stored in database (not S3). 8k token budget (6k skills + 2k learnings).
- **AD-5:** Multi-file artifacts: S3 directory + JSONB `file_manifest` on `ArtifactVersion`.
- **AD-6:** Diffs computed on-the-fly by frontend. No diff storage.
- **AD-7:** pgvector for uploaded documents only (not agent skills).
- **AD-8:** Hardcoded DAG templates + LLM router (5 MVP templates).
- **AD-14:** GitHub/GitLab auth via PAT only (no OAuth for MVP).
- **AD-15:** Artifact files served via backend proxy (not pre-signed URLs).
- **AD-16:** Cursor-based pagination on all list endpoints.
- **AD-19:** Fresh design system. oklch colors. Do NOT inherit V1 tokens.
- **AD-23:** Both light and dark mode from day one.

## Documentation Map

Read the TDDs **before** implementing anything. Each ticket in the roadmap cites its source TDD sections.

| File | Contents |
|---|---|
| `docs/TDD/01_PRD_AND_WORKFLOWS.md` | Product requirements, user personas, 6 user journeys (J1-J6), artifact state machine, edge cases |
| `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md` | 12 database tables, S3 layout, Celery tasks, circuit breakers, reflection locking, Docker services |
| `docs/TDD/03_AI_AGENT_ENGINE_TDD.md` | Sufficiency check, 5 DAG templates, auto-assembly router, prompt architecture (9-position), memory management, 7 tools, reflection engine |
| `docs/TDD/04_API_AND_INTEGRATIONS_TDD.md` | 44 REST endpoints with full request/response schemas, GitHub/GitLab webhooks, MCP, WebSocket events |
| `docs/TDD/05_FRONTEND_UX_TDD.md` | Route tree, design tokens, state management, API client, Smart Brief form, heartbeat UI, review/diff/comments UX |
| `docs/TDD/06_IMPLEMENTATION_ROADMAP.md` | 49 tickets across 12 sprints in strict dependency order. **This is the execution plan.** |

## Database Schema (12 tables)

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

All tables use `TEXT` PKs (UUID v4, generated in Python). All timestamps `TIMESTAMPTZ`. See TDD-02 Section 1.2 for full column definitions.

## Core Domain Model

- **Artifact** = a deliverable (not a task). States: `drafting` → `in_review` → `approved` (+ `cancelled`).
- **ArtifactVersion** = one version of the output. S3 file bundle + JSONB manifest.
- **ExecutionWave** = one execution run. Contains `dag_plan`, `assembled_team`, heartbeat fields.
- **Agent** = persistent AI entity in the roster. Has skills, learnings, readiness score.
- **AgentSkill** = knowledge entry. Categories: `skill`, `work_learning`, `briefing`.

## Backend Conventions

- **Models:** One file per model in `app/models/`. Import all from `app/models/__init__.py`.
- **Routes:** One file per domain in `app/api/routes/`. Register in `app/main.py`.
- **Business logic:** In `app/core/` (infrastructure) and `app/agents/` (AI engine).
- **Error format:** `{ "error": { "code": "...", "message": "...", "details": {} } }` — see TDD-04 Section 1.4.
- **Pagination:** Cursor-based. `PaginatedResponse[T]` with `items`, `next_cursor`, `has_more`.
- **Workspace isolation:** `get_workspace_id()` FastAPI dependency returns `"1"` for MVP.
- **Async:** All DB operations use async SQLAlchemy sessions.
- **Tests:** Put in `backend/tests/`. Integration tests use real PostgreSQL + MinIO.

## Frontend Conventions

- **App Router:** All pages in `app/`. Feature components in `features/`. Shared components in `components/`.
- **Design tokens:** CSS custom properties in `app/tokens.css`. oklch color space. Never use raw hex.
- **State:** Server state = TanStack Query. UI state = Zustand. URL state for navigation params.
- **API client:** `lib/api-client.ts` base, `lib/api/index.ts` domain methods. All typed.
- **Forms:** React Hook Form + Zod schemas.
- **Fonts:** Inter (sans), JetBrains Mono (mono).

## Sprint Overview

| Sprint | Focus | Tickets |
|---|---|---|
| 0 | Project scaffold + Docker + dependencies | 0.1 |
| 1 | Database schema (models + migrations) | 1.1-1.2 |
| 2 | Core backend services (S3, cost, Celery, utils) | 2.1-2.4 |
| 3 | AI foundation (agent loop, tools, prompts, memory) | 3.1-3.5 |
| 4 | DAG & orchestration (templates, router, orchestrator) | 4.1-4.4 |
| 5 | Sufficiency, memory, reflection | 5.1-5.5 |
| 6 | API routes core (onboarding, roster, projects, artifacts) | 6.1-6.5 |
| 7 | API routes integrations (git, webhooks, MCP, WS) | 7.1-7.6 |
| 8 | Frontend scaffold (Next.js, tokens, shell, API client) | 8.1-8.4 |
| 9 | Frontend core flows (onboarding, brief, heartbeat, review) | 9.1-9.6 |
| 10 | Frontend settings & polish | 10.1-10.3 |
| 11 | Integration & QA (E2E flows, edge cases, perf) | 11.1-11.4 |

**Parallelization note:** Sprint 8 (frontend scaffold) can start alongside Sprints 6-7 since API contracts are defined in TDD-04.

## Common Commands

```bash
# Infrastructure
docker compose up postgres redis minio      # Start data services
docker compose up                            # Start all services

# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
celery -A app.core.celery_app worker --concurrency=1 --loglevel=info
celery -A app.core.celery_app beat --loglevel=info

# Database
alembic upgrade head                         # Run migrations
alembic downgrade base                       # Tear down all tables

# Frontend
cd frontend
pnpm install
pnpm dev                                     # Start at :3000
pnpm build                                   # Production build

# Verify
python -c "from app.main import app"         # Import check after changes
```

## Do NOT

- Write any code outside the roadmap ticket sequence without explicit approval
- Change architectural decisions (AD-1 through AD-23) without discussion
- Create V1-style task/team/chat models — V2 is artifact-centric
- Use OAuth for git providers (PAT only for MVP)
- Store diffs in the database (compute on-the-fly in frontend)
- Add a conversational chatbot interface (this is not a chatbot)
- Use pre-signed S3 URLs (backend proxy only)
- Skip the verify step on any ticket
