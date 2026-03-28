# AI Agent Team Orchestrator — V2 "Artifact-First"

## What This Is

An AI-powered autonomous agency for knowledge work and code. Users write a brief, a cross-functional team of specialized AI agents collaborates to produce the deliverable, and the user reviews and iterates on the output through version-controlled diffs.

**One-liner:** *You write the brief. We deliver the work. You review the diff.*

## Project Status

**V2 implementation complete.** All 12 sprints (49 tickets) executed. 78 E2E tests passing. All 6 user journeys verified. All edge cases from TDD-01 Section 6 covered. Performance baselines within targets.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| Object Storage | MinIO (S3-compatible) |
| AI | Anthropic Claude API (Sonnet/Opus/Haiku tiers) |
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| State | Zustand (UI), TanStack Query (server), URL params (navigation) |
| Infrastructure | Docker Compose (postgres, redis, minio, backend, worker, beat, frontend) |

## Architecture — Key Decisions

Locked decisions from the TDD process. Do not change without explicit approval.

- **AD-1:** Single-tenant MVP. All tables have `workspace_id` FK. Hardcoded `workspace_id = "1"`.
- **AD-2:** Celery + Redis for execution (not Temporal).
- **AD-3:** One orchestrator Celery task per execution. `asyncio.gather` for parallel waves.
- **AD-4:** Agent skills in database (not S3). 8k token budget (6k skills + 2k learnings).
- **AD-5:** Multi-file artifacts: S3 directory + JSONB `file_manifest` on `ArtifactVersion`.
- **AD-6:** Diffs computed on-the-fly by frontend. No diff storage.
- **AD-7:** pgvector for uploaded documents only (not agent skills).
- **AD-8:** Hardcoded DAG templates + LLM router (5 MVP templates).
- **AD-14:** GitHub/GitLab auth via PAT only (no OAuth for MVP).
- **AD-15:** Artifact files served via backend proxy (not pre-signed URLs).
- **AD-16:** Cursor-based pagination on all list endpoints.
- **AD-19:** Fresh design system. oklch colors.
- **AD-23:** Both light and dark mode from day one.

## Codebase Map

### Backend (`backend/app/`)

```
app/
├── main.py                    # FastAPI app, CORS, lifespan, error handler registration
├── config/settings.py         # Pydantic Settings: DB, Redis, S3, Anthropic, model tiers
├── models/                    # 12 SQLAlchemy models (one per file) + enums.py
│   ├── workspace.py, agent.py, agent_skill.py, project.py
│   ├── artifact.py, artifact_version.py, execution_wave.py
│   ├── contextual_comment.py, document.py, document_chunk.py
│   ├── git_provider_connection.py, mcp_connection.py
│   └── enums.py               # All PostgreSQL enum types
├── core/                      # Infrastructure services
│   ├── database.py            # AsyncSession factory, Base, get_db dependency
│   ├── celery_app.py          # Celery config, 4 tasks + 2 periodic tasks
│   ├── s3_workspace.py        # Upload/download/delete for artifacts + documents
│   ├── cost.py                # Decimal pricing table, budget checks, atomic increments
│   ├── pagination.py          # Cursor encode/decode, PaginatedResponse[T], LIMIT+1
│   ├── errors.py              # ApiError, error factories, FastAPI exception handler
│   ├── workspace_id.py        # get_workspace_id() → hardcoded "1"
│   ├── encryption.py          # Fernet encrypt/decrypt for PATs and auth configs
│   ├── git_push.py            # push_artifact_to_git, push_iteration_to_git
│   ├── git_providers/         # github.py, gitlab.py, common.py (shared protocol)
│   ├── mcp_client.py          # MCP protocol client
│   ├── reaper.py              # reap_orphaned_waves (>10min running)
│   └── billing.py             # reset_monthly_budgets (>30 days)
├── agents/                    # AI engine
│   ├── anthropic_runner.py    # run_agent() loop: send → tool_use → repeat → end_turn
│   ├── orchestrator.py        # execute_dag(): wave loop, parallel slots, S3 upload, version creation
│   ├── router.py              # route_brief(): Haiku call → template + agent mapping
│   ├── prompt_builder.py      # 9-position prompt: system (1-3) + user (4-9, recency bias)
│   ├── memory.py              # load_agent_memory, check_budget, trigger_compaction
│   ├── upstream.py            # build_upstream_context, truncate_middle (47/53 split, 15k cap)
│   ├── sufficiency.py         # run_sufficiency_check (Sonnet), fail-open policy
│   ├── readiness.py           # compute_readiness_score (heuristic: 40+30+20+10)
│   ├── learning.py            # execute_learning: web research → skill extraction
│   ├── reflection.py          # execute_reflection: FOR UPDATE lock, Sonnet review, skill updates
│   ├── briefing.py            # brief_all_agents: distribute project brief to roster
│   ├── document_processor.py  # PDF/DOCX/text extraction → 512-token chunks → pgvector
│   └── dag_templates/         # schema.py + 5 templates (code_feature, content_research, etc.)
├── api/
│   ├── routes/                # 10 files: onboarding, roster, projects, artifacts, git_providers,
│   │                          #   webhooks, mcp, usage, health, (+ websocket endpoint)
│   ├── schemas/               # 7 files: Pydantic request/response models per domain
│   └── websocket_manager.py   # Connection tracking, broadcast_event, 5 event types
└── tools/                     # 7 agent tools
    ├── registry.py            # get_tools_for_phase() — availability matrix
    ├── web_search.py          # Serper API
    ├── web_browser.py         # httpx + BeautifulSoup, 8k truncation
    ├── vector_search.py       # pgvector cosine similarity on document_chunks
    ├── file_read.py           # In-memory dict (scoped per execution)
    ├── file_write.py          # In-memory dict (scoped per execution)
    ├── mcp_call.py            # MCP server proxy, 30s timeout
    └── git_tools.py           # git_clone + git_push wrappers
```

### Frontend (`frontend/`)

```
app/                           # Next.js App Router
├── layout.tsx                 # Root: providers, fonts, tokens
├── tokens.css                 # oklch design tokens (light + dark)
├── (onboarding)/onboarding/   # Multi-step onboarding wizard
└── (app)/                     # Main app shell (sidebar + top bar)
    ├── projects/              # Project list → detail → brief → documents
    │   └── [projectId]/artifacts/
    │       ├── new/           # Smart Brief form + delegation
    │       └── [artifactId]/  # Heartbeat OR review (based on status)
    ├── roster/                # Agent grid → agent detail (profile, skills, history)
    └── settings/{git,mcp,usage}/  # Integration + billing settings

features/                      # Feature-specific components
├── artifacts/                 # smart-brief-form, heartbeat-panel, artifact-review,
│                              #   prose-viewer, prose-diff-viewer, version-switcher, etc.
├── comments/                  # floating-comment-toolbar (Selection API + positioning)
├── onboarding/                # onboarding-form, roster-preview
├── projects/                  # brief-editor (auto-save), document-manager (drag-drop)
└── roster/                    # agent-card, agent-detail-tabs, research-dialog

lib/
├── api-client.ts              # Base fetch wrapper, error interceptor
├── api/                       # 7 domain files covering all 44 endpoints (typed)
├── hooks/                     # TanStack Query hooks + use-websocket + use-text-selection
├── stores/                    # ui-store (sidebar, theme, diff mode) + selection-store
├── query-keys.ts              # Query key factory with stale times per data type
└── types/api.ts               # All TypeScript API types
```

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

8 Alembic migrations in FK-dependency order. All tables use `TEXT` PKs (UUID v4). All timestamps `TIMESTAMPTZ`.

### Tests

```
backend/tests/
├── test_*.py              # Unit + integration tests per module
└── e2e/                   # 78 end-to-end tests
    ├── test_prose_flow.py     # Journey J2 (21 tests)
    ├── test_code_flow.py      # Journey J3 (15 tests)
    ├── test_edge_cases.py     # TDD-01 Section 6 (27 tests)
    └── test_performance.py    # Baseline metrics (15 tests)
```

## Core Domain Model

- **Artifact** = a deliverable (not a task). States: `drafting` → `in_review` → `approved` (+ `cancelled`).
- **ArtifactVersion** = immutable version. S3 file bundle + JSONB manifest.
- **ExecutionWave** = one execution run. `dag_plan`, `assembled_team`, heartbeat fields.
- **Agent** = persistent AI entity in the roster. Skills, learnings, readiness score.
- **AgentSkill** = knowledge entry. Categories: `skill`, `work_learning`, `briefing`.

## Documentation

| File | Contents |
|---|---|
| `docs/TDD/01_PRD_AND_WORKFLOWS.md` | User personas, 6 journeys (J1-J6), state machine, edge cases |
| `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md` | 12 tables, S3 layout, Celery tasks, circuit breakers |
| `docs/TDD/03_AI_AGENT_ENGINE_TDD.md` | Sufficiency, DAG templates, prompts, memory, 7 tools, reflection |
| `docs/TDD/04_API_AND_INTEGRATIONS_TDD.md` | 44 endpoints with full request/response schemas |
| `docs/TDD/05_FRONTEND_UX_TDD.md` | Design tokens, routes, state, Smart Brief, heartbeat, review UX |
| `docs/TDD/06_IMPLEMENTATION_ROADMAP.md` | 49 tickets across 12 sprints (all complete) |

## Common Commands

```bash
# Infrastructure
docker compose up postgres redis minio      # Start data services
docker compose up                            # Start everything

# Backend (from backend/)
pip install -r requirements.txt
alembic upgrade head                         # Run migrations
uvicorn app.main:app --reload --port 8000    # API server
celery -A app.core.celery_app worker --concurrency=1 --loglevel=info
celery -A app.core.celery_app beat --loglevel=info

# Frontend (from frontend/)
pnpm install
pnpm dev                                     # Dev server at :3000
pnpm build                                   # Production build

# Tests
cd backend && pytest tests/ -v               # Unit + integration
cd backend && pytest tests/e2e/ -v           # End-to-end (needs Docker services)
```

## Known Issues / Post-Launch Debt

- Frontend E2E tests (Playwright/Cypress) not yet set up — no testing framework in `frontend/package.json`
- Performance measurements are with mocked DB/LLM; need real-service benchmarks after Docker deployment
- Webhook deduplication tested at handler-mock level; full `IntegrityError` path needs live DB test
- No `GET /api/projects/{id}` route exists (only `/context` and `PATCH`) — may want to add a project detail endpoint
- Budget exceeded returns 429 — confirm this is the desired status code vs 402/403

## Do NOT

- Change architectural decisions (AD-1 through AD-23) without discussion
- Create V1-style task/team/chat models — V2 is artifact-centric
- Use OAuth for git providers (PAT only for MVP)
- Store diffs in the database (compute on-the-fly in frontend)
- Add a conversational chatbot interface (this is not a chatbot)
- Use pre-signed S3 URLs (backend proxy only)
