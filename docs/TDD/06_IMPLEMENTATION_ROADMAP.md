# Phase 6 — Implementation Roadmap

> **Document type:** Implementation Plan
> **Status:** Draft
> **Source of truth:** `docs/TDD/01_PRD_AND_WORKFLOWS.md` through `docs/TDD/05_FRONTEND_UX_TDD.md`
> **Scope:** Strictly ordered, dependency-aware coding tickets. Each ticket produces a testable outcome. No architecture — that's settled in TDDs 01-05.

---

## How to Use This Document

1. **Execute tickets in order.** Each ticket lists its dependencies. Do not skip ahead.
2. **One ticket = one commit (or small PR).** Keep changes atomic and reviewable.
3. **Test before moving on.** Each ticket ends with a **Verify** section. Do not start the next ticket until verification passes.
4. **Reference the TDDs.** Each ticket cites the exact TDD section(s) it implements. Read those sections before coding.

---

## Codebase Starting Point

| Layer | Current State |
|---|---|
| **Backend** | Clean slate. All V1 code has been removed. Everything is written from scratch. |
| **Docker** | Nothing. `docker-compose.yml` created in Ticket 0.1. |
| **Alembic** | Nothing. Initialized in Ticket 0.2. |
| **Frontend** | Nothing. Initialized in Sprint 8. |

### Approach: Full Clean Slate

All V1 code has been deleted. Every module — including infrastructure files that were originally earmarked for reuse (settings, database, S3, Celery, Anthropic runner, tool registry, git providers, MCP client, WebSocket manager) — is written fresh from the TDD specs. This avoids carrying forward any V1 assumptions or technical debt.

---

## Sprint 0: Infrastructure & Clean Slate

### Ticket 0.1 — Project scaffold + Docker infrastructure

**Ref:** TDD-02 Section 9

**Goal:** Create the backend project structure from scratch and set up Docker Compose with all services.

**Create `backend/` directory structure:**
```
backend/
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app with CORS, lifespan, error handlers
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py      # Pydantic Settings: DB, Redis, S3, Anthropic, model tiers
│   ├── core/
│   │   ├── __init__.py
│   │   └── database.py      # AsyncSession factory (async SQLAlchemy + asyncpg)
│   ├── models/
│   │   └── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       └── __init__.py
│   ├── agents/
│   │   └── __init__.py
│   └── tools/
│       └── __init__.py
└── tests/
    └── __init__.py
```

**Create `backend/app/config/settings.py`:**
- Pydantic `Settings` class with: `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME` (default `agent-artifacts`), `ANTHROPIC_API_KEY`, `MODEL_SONNET` (default `claude-sonnet-4-20250514`), `MODEL_HAIKU` (default `claude-haiku-4-5-20251001`), `MODEL_OPUS` (default `claude-opus-4-20250514`), `SERPER_API_KEY` (optional), `CORS_ORIGINS` (default `["http://localhost:3000"]`).
- Load from `.env` file.

**Create `backend/app/core/database.py`:**
- `engine` = `create_async_engine(settings.DATABASE_URL)`.
- `async_session_maker` = `async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`.
- `get_db()` async generator dependency for FastAPI.
- `Base` = SQLAlchemy `DeclarativeBase`.

**Create `backend/app/main.py`:**
- FastAPI app with CORS middleware (origins from settings).
- Empty lifespan (placeholder for S3 bucket init).
- No routes registered yet (added in later sprints).

**Create `backend/Dockerfile`:**
- Python 3.12-slim base. Install requirements. Copy app. Uvicorn entrypoint.

**Create `backend/.env.example`:**
- All settings with placeholder values.

**Create `docker-compose.yml` (project root):**
- `postgres` service: postgres:16 with pgvector extension, port 5432, persistent volume.
- `redis` service: redis:7-alpine, port 6379.
- `minio` service: minio/minio, ports 9000/9001, persistent volume.
- `backend` service: builds from `backend/Dockerfile`, port 8000, depends on postgres/redis/minio, mounts backend code for dev.
- `worker` service: same image as backend, command `celery -A app.core.celery_app worker --concurrency=1 --loglevel=info`.
- `beat` service: same image as backend, command `celery -A app.core.celery_app beat --loglevel=info`.
- `frontend` service: node:20, port 3000, mounts frontend code (created in Sprint 8).
- All services share the same `.env` file.

**Create `backend/requirements.txt`:**
- `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `celery[redis]`, `redis`, `boto3`, `anthropic`, `pydantic`, `pydantic-settings`
- `pgvector` (SQLAlchemy pgvector extension), `pymupdf` (PDF extraction), `python-docx` (DOCX extraction), `beautifulsoup4` (HTML-to-text), `httpx` (async HTTP for tools), `python-multipart` (file uploads)

**Initialize Alembic:**
- `alembic.ini` pointing at `alembic/` directory.
- `alembic/env.py` configured for async SQLAlchemy with `Base.metadata` target.

**Verify:**
- `pip install -r backend/requirements.txt` succeeds.
- `python -c "from app.main import app"` succeeds (run from `backend/`).
- `python -c "from app.core.database import async_session_maker, Base"` succeeds.
- `python -c "import pgvector; import fitz; import docx; import bs4; import httpx"` succeeds.
- `docker compose up postgres redis minio` starts all infrastructure services with healthy status.
- Backend, worker, beat, frontend services are defined (they won't fully start until later tickets provide the required modules).

---

## Sprint 1: Database Schema

### Ticket 1.1 — Create V2 SQLAlchemy models

**Ref:** TDD-02 Section 1.2 (all 12 table definitions)

**Goal:** Write the complete V2 SQLAlchemy model layer in `app/models/`. One model per file, matching the TDD-02 schema exactly.

**Create these files:**
- `app/models/workspace.py` — `Workspace` model
- `app/models/agent.py` — `Agent` model with all V2 columns (readiness_score, progression_level, model_tier, tools JSONB, completed_artifacts, avg_quality_score, last_reflection_at, archived_at)
- `app/models/agent_skill.py` — `AgentSkill` model (category enum: skill/work_learning/briefing, token_count, source_artifact_id)
- `app/models/project.py` — `Project` model with brief_draft, brief_published, brief_fingerprint, brief_published_at
- `app/models/artifact.py` — `Artifact` model with all V2 columns (artifact_type, goal, target_audience, context, description, status enum, budget, cost, git fields)
- `app/models/artifact_version.py` — `ArtifactVersion` model (s3_prefix, file_manifest JSONB, assumptions JSONB, sources JSONB, execution_wave_id)
- `app/models/contextual_comment.py` — `ContextualComment` model (source enum, external_comment_id, resolved, resolved_in_version_id)
- `app/models/execution_wave.py` — `ExecutionWave` model (trigger enum, dag_plan JSONB, assembled_team JSONB, status enum, current_step, total_steps, step_labels JSONB, cost tracking, error_message)
- `app/models/document.py` — `Document` model (processing_status enum)
- `app/models/document_chunk.py` — `DocumentChunk` model (embedding vector(1024), chunk_index, token_count)
- `app/models/git_provider_connection.py` — `GitProviderConnection` model (access_token_encrypted, repositories JSONB, webhook_secret)
- `app/models/mcp_connection.py` — `McpConnection` model (auth_config_encrypted JSONB, discovered_tools JSONB)

**Write:** `app/models/__init__.py` — export all models. Import `Base` from SQLAlchemy declarative base.

**Convention:** All models use `TEXT` primary keys (UUID v4 generated in Python). All timestamps use `TIMESTAMP WITH TIME ZONE`. All tables include `workspace_id` FK except `workspaces` itself.

**Verify:**
- `python -c "from app.models import Workspace, Agent, AgentSkill, Project, Artifact, ArtifactVersion, ContextualComment, ExecutionWave, Document, DocumentChunk, GitProviderConnection, McpConnection"` succeeds.
- All 12 models have correct column types and FK relationships matching TDD-02 Section 1.2.

---

### Ticket 1.2 — Write Alembic migrations

**Ref:** TDD-02 Section 8

**Goal:** Create the full V2 schema as Alembic migrations from scratch.

**Steps:**
1. Create migrations in FK-dependency order:
   - Migration 1: Enable pgvector extension. Create `workspaces`.
   - Migration 2: Create `agents`, `projects`.
   - Migration 3: Create `agent_skills`, `documents`, `git_provider_connections`, `mcp_connections`.
   - Migration 4: Create `artifacts`.
   - Migration 5: Create `execution_waves`.
   - Migration 6: Create `artifact_versions`.
   - Migration 7: Create `contextual_comments`, `document_chunks`.
   - Migration 8: Seed default workspace (id = hardcoded UUID, name = "Default Workspace", `onboarding_completed = false`).
3. Include all indexes defined in TDD-02 (partial indexes, unique constraints).

**Verify:**
- `alembic upgrade head` runs clean against a fresh database.
- `alembic downgrade base` removes all tables.
- `alembic upgrade head` again — idempotent.
- Verify with `\dt` in psql that all 12 tables exist with correct columns.

---

## Sprint 2: Core Backend Services

### Ticket 2.1 — S3 workspace module

**Ref:** TDD-02 Section 4

**Goal:** Create `app/core/s3_workspace.py` from scratch with V2 path conventions.

**Functions to implement:**
- `upload_artifact_file(artifact_id, version_number, file_path, content)` → writes to `artifacts/{artifact_id}/v{version}/{file_path}`
- `download_artifact_file(artifact_id, version_number, file_path)` → reads and returns content
- `upload_document(document_id, filename, file_bytes)` → writes to `documents/{document_id}/{filename}`
- `download_document(document_id, filename)` → reads and returns content
- `delete_artifact_version(artifact_id, version_number)` → deletes all files under the prefix
- `delete_document(document_id)` → deletes all files under the prefix
- `ensure_bucket()` → creates the `agent-artifacts` bucket if it doesn't exist (for dev startup)

**Verify:**
- Unit test: upload a file, download it, verify content matches.
- Unit test: list files under a prefix returns correct paths.
- Unit test: delete removes the files.

---

### Ticket 2.2 — Cost calculation utilities

**Ref:** TDD-02 Section 5.2

**Goal:** Create `app/core/cost.py` with pricing table and cost computation.

**Implement:**
- `PRICING` dict with per-1K-token rates for sonnet, opus, haiku (from TDD-02 Section 5.2).
- `compute_call_cost(input_tokens, output_tokens, model)` → returns `Decimal`.
- `check_artifact_budget(artifact_id, additional_cost)` → returns `(allowed: bool, remaining: Decimal)`.
- `check_monthly_budget(workspace_id, additional_cost)` → returns `(allowed: bool, remaining: Decimal)`.
- `increment_costs(execution_wave_id, artifact_id, workspace_id, cost)` → atomic DB updates to wave, artifact, and workspace cost columns.

**Verify:**
- Unit test: `compute_call_cost(1000, 500, "sonnet")` returns expected value.
- Unit test: budget check returns `False` when cost exceeds limit.

---

### Ticket 2.3 — Celery app + task registration

**Ref:** TDD-02 Section 3.2

**Goal:** Create `app/core/celery_app.py` from scratch with Celery configuration and register V2 tasks (stubs for now — logic comes later).

**Create `app/core/celery_app.py`:**
- Register `execute_artifact_dag(execution_wave_id: str)` with config: `acks_late=True`, `max_retries=0`, `soft_time_limit=600`, `time_limit=660`.
- Register `process_document_upload(document_id: str)` with config: `max_retries=3`, `retry_backoff=True`, `soft_time_limit=120`.
- Register `execute_agent_learning(agent_id: str)` with config: `soft_time_limit=300`.
- Register `execute_agent_reflection(agent_id: str)` with config: `soft_time_limit=120`.
- Register periodic task `reap_orphaned_waves` — every 2 minutes.
- Register periodic task `reset_monthly_budgets` — daily at 00:00 UTC.

All task bodies are stubs (`pass` or `raise NotImplementedError`) — implementation comes in later tickets.

**Verify:**
- Celery worker starts without errors: `celery -A app.core.celery_app worker --loglevel=info`.
- Celery beat starts and schedules periodic tasks.

---

### Ticket 2.4 — Shared backend utilities

**Goal:** Create utility modules referenced across the backend.

**Create `app/core/workspace_id.py`:**
- `get_workspace_id()` FastAPI dependency — returns hardcoded `"1"` for MVP (TDD-04 Section 1.2).

**Create `app/core/pagination.py`:**
- `encode_cursor(item)` — base64-encode sort keys.
- `decode_cursor(cursor_str)` — decode.
- `apply_cursor_pagination(query, cursor, limit)` — apply WHERE clause and LIMIT+1 pattern (TDD-04 Section 1.3).
- Pydantic `PaginatedResponse[T]` model with `items`, `next_cursor`, `has_more`.

**Create `app/core/errors.py`:**
- `ApiError` exception class with `code`, `message`, `status_code`, `details`.
- FastAPI exception handler that returns the standard error envelope (TDD-04 Section 1.4).

**Verify:**
- Unit test: cursor encode/decode roundtrips.
- Unit test: ApiError serializes to correct JSON format.

---

## Sprint 3: AI Engine — Foundation

### Ticket 3.1 — Agent execution loop

**Ref:** TDD-03 Section 6.4

**Goal:** Create `app/agents/anthropic_runner.py` from scratch — the V2 agent execution loop.

**Implement `run_agent()` function (TDD-03 Section 6.4 pseudocode):**
- Takes: `system_prompt`, `user_message`, `tools`, `model`, `max_iterations=15`, `max_tokens=8192`.
- Returns: `AgentResult(text, files, input_tokens, output_tokens, assumptions, sources)`.
- Loop: send messages → if `stop_reason == "end_turn"`, extract text + files → return. If `stop_reason == "tool_use"`, execute tools, append results, continue.
- Extract assumptions via regex `[ASSUMPTION: ...]` (TDD-03 Section 7.3).
- Extract sources via regex `[Source: ...]`.
- Track cumulative token usage.
- Raise `AgentMaxIterationError` if loop exhausts max_iterations.

**Verify:**
- Integration test with a mock Anthropic client: agent receives a prompt, calls one tool, produces output.
- Unit test: assumption extraction regex works on sample text.

---

### Ticket 3.2 — Tool definitions and executors

**Ref:** TDD-03 Section 6.2-6.3

**Goal:** Implement the 7 MVP tools with their executors.

**Create `app/tools/` modules:**
- `web_search.py` — Calls Serper API (or equivalent). Returns formatted results. Add `SERPER_API_KEY` to settings.
- `web_browser.py` — HTTP GET via `httpx`, HTML-to-text via BeautifulSoup, truncate to 8,000 chars.
- `vector_search.py` — Embeds query, runs pgvector cosine similarity on `document_chunks`. Returns top-K chunks with filename.
- `file_read.py` / `file_write.py` — Read/write to an in-memory dict (scoped to the execution). No filesystem access.
- `mcp_call.py` — Proxy call to MCP server. Timeout 30s. Dynamically generated tool definitions from `discovered_tools`.
- `git_tools.py` — `git_clone` and `git_push` wrappers (thin layer over `app/core/git_providers/`).

**Create `app/tools/registry.py`:**
- `get_tools_for_phase(phase, workspace_mcp, workspace_git)` — returns the correct tool subset per TDD-03 Section 6.2 availability matrix.

**Verify:**
- Unit test: `web_browser` tool extracts text from a sample HTML string.
- Unit test: `file_write` stores content, `file_read` retrieves it.
- Unit test: `get_tools_for_phase("execution", [...], [...])` returns all tools; `get_tools_for_phase("reflection", [], [])` returns only file tools.

---

### Ticket 3.3 — Prompt assembly

**Ref:** TDD-03 Section 4 (full prompt structure), Section 7 (auto-assume)

**Goal:** Create `app/agents/prompt_builder.py` — assembles the complete prompt for an agent execution call.

**Implement:**
- `build_system_prompt(agent, output_format_rules)` — positions 1-3: role + auto-assume rule + output format.
- `build_user_message(agent_memory, upstream_context, project_brief, artifact_brief, wave_task)` — positions 4-9 in exact recency bias order.
- `build_iteration_prompt(previous_version_content, comment, artifact_brief)` — the modified prompt for contextual iterations (TDD-03 Section 4.5).
- `get_output_format_rules(artifact_type, slot_role)` — returns the correct format rules (prose/code/analysis/QA from TDD-03 Section 4.4).
- Auto-assume rule text is a constant string (TDD-03 Section 7.2).

**Verify:**
- Unit test: `build_user_message()` output has sections in correct order — skills before upstream before project brief before artifact brief before task (recency bias rule).
- Unit test: auto-assume text is present in every system prompt.

---

### Ticket 3.4 — Agent memory loader

**Ref:** TDD-03 Section 5

**Goal:** Create `app/agents/memory.py` — loads agent skills into prompt context.

**Implement:**
- `load_agent_memory(agent_id)` — queries `agent_skills` for `skill` + `work_learning` categories, formats as markdown sections, returns string. (TDD-03 Section 5.4)
- `check_memory_budget(agent_id)` — returns current total tokens and remaining budget.
- `trigger_compaction(agent_id)` — runs the Sonnet compaction call (TDD-03 Section 5.3), replaces existing entries with compacted versions.
- Token counting via `anthropic.count_tokens()` or `tiktoken`.

**Verify:**
- Unit test: `load_agent_memory()` formats skills correctly with `## Skill:` and `## Work Learning:` headers.
- Unit test: `check_memory_budget()` returns accurate token count from DB.

---

### Ticket 3.5 — Upstream context builder

**Ref:** TDD-03 Section 8

**Goal:** Create `app/agents/upstream.py` — builds cross-functional context for downstream agents.

**Implement:**
- `build_upstream_context(wave, wave_outputs)` — iterates `depends_on` slot IDs, concatenates upstream outputs with headers.
- `truncate_middle(text, max_tokens=15000)` — middle-out truncation: keep first 47%, insert truncation marker, keep last 53%. (TDD-03 Section 8.2)

**Verify:**
- Unit test: `truncate_middle()` on a 20,000-token string returns ~15,000 tokens with the marker in the middle.
- Unit test: `build_upstream_context()` assembles correct sections from a mock `wave_outputs` dict.

---

## Sprint 4: AI Engine — DAG & Orchestration

### Ticket 4.1 — DAG template library

**Ref:** TDD-03 Section 2

**Goal:** Create `app/agents/dag_templates/` with the 5 MVP templates.

**Implement:**
- `app/agents/dag_templates/schema.py` — `DagSlot`, `DagWave`, `DagTemplate` dataclasses (TDD-03 Section 2.2).
- `app/agents/dag_templates/code_feature.py` — 3-wave template (TDD-03 Section 2.3).
- `app/agents/dag_templates/content_research.py` — 3-wave template.
- `app/agents/dag_templates/simple_prose.py` — 2-wave template.
- `app/agents/dag_templates/code_bugfix.py` — 3-wave template.
- `app/agents/dag_templates/multi_research.py` — 2-wave template.
- `app/agents/dag_templates/__init__.py` — `TEMPLATE_REGISTRY: dict[str, DagTemplate]` mapping template_id to instance.

**Verify:**
- Unit test: all 5 templates are registered.
- Unit test: each template has valid wave/slot structure (no duplicate slot_ids within a wave, all `depends_on` reference existing slots).

---

### Ticket 4.2 — Auto-assembly & DAG router

**Ref:** TDD-03 Section 3

**Goal:** Create `app/agents/router.py` — the Haiku call that selects a template and maps agents.

**Implement:**
- `route_brief(artifact, roster_agents)` → calls Haiku with system prompt (TDD-03 Section 3.2) and user message (TDD-03 Section 3.3). Parses JSON response (TDD-03 Section 3.4).
- Post-router processing (TDD-03 Section 3.5): validate response, build `dag_plan` JSONB, build `assembled_team`, build `step_labels`, filter agents below readiness gate.
- `estimate_cost(template, model_tier)` → rough estimate (TDD-03 Section 3.6).
- Fallback: if Haiku call fails or returns invalid JSON, default to `simple_prose` template with the most general agent.

**Verify:**
- Integration test: mock Haiku response, verify `dag_plan` JSONB is correctly hydrated.
- Unit test: `estimate_cost("code_feature", "sonnet")` returns ~$0.17 (4 slots × $0.042).

---

### Ticket 4.3 — execute_artifact_dag orchestrator

**Ref:** TDD-02 Section 3.2, TDD-03 Section 13 (end-to-end flow)

**Goal:** Implement the complete `execute_artifact_dag` Celery task. This is the core of the system.

**Implement the lifecycle from TDD-03 Section 13:**
1. **LOAD:** Read ExecutionWave, Artifact, Project from DB. Set wave status = `running`.
2. **WAVE LOOP:** For each wave sequentially:
   a. Update heartbeat (`current_step`, cost).
   b. For each slot concurrently (`asyncio.gather`): load agent → load memory → build upstream context → build tools → assemble prompt → run agent loop → extract assumptions/sources → collect files → accumulate tokens/cost.
   c. Store outputs in `wave_outputs` dict.
   d. Check circuit breaker — abort if over budget.
3. **COMPILE:** If `template.needs_compile`, run compile agent.
4. **FINALIZE:** Merge files → upload to S3 → create `ArtifactVersion` row → update artifact status to `in_review` → update costs.
5. **CODE ARTIFACTS:** If `artifact_type == "code"`, trigger git push flow (stub — implemented in Sprint 6).
6. **ERROR PATH:** On failure after retries, set wave status = `failed`, leave artifact in `drafting`.

**Verify:**
- Integration test with mock Anthropic client: create an artifact + wave, run the task, verify an `ArtifactVersion` is created with correct `file_manifest` and files exist in S3 (MinIO).
- Integration test: circuit breaker aborts when cost exceeds `max_budget_usd`.
- Integration test: heartbeat updates (`current_step`, `cost_usd`) are written to DB during execution.

---

### Ticket 4.4 — Reaper and monthly reset periodic tasks

**Ref:** TDD-02 Section 3.2 (reap_orphaned_waves), Section 5.4 (reset_monthly_budgets)

**Goal:** Implement the two periodic Celery Beat tasks.

**Implement:**
- `reap_orphaned_waves()` — finds waves in `running` status for > 10 minutes, checks if Celery task is alive, marks dead waves as `failed`. (TDD-02 Section 3.2, reaper spec)
- `reset_monthly_budgets()` — resets `monthly_spend_usd` for workspaces where `billing_period_start` is > 30 days old. (TDD-02 Section 5.4)

**Verify:**
- Unit test: create a wave with `started_at` 15 minutes ago and `status = 'running'`, run the reaper, verify status is now `failed`.
- Unit test: create a workspace with `billing_period_start` 35 days ago, run the reset, verify `monthly_spend_usd = 0`.

---

## Sprint 5: AI Engine — Sufficiency, Memory, Reflection

### Ticket 5.1 — Sufficiency check engine

**Ref:** TDD-03 Section 1

**Goal:** Create `app/agents/sufficiency.py` — the Sonnet-powered brief validator.

**Implement:**
- `run_sufficiency_check(artifact, workspace)` → builds the system prompt (TDD-03 Section 1.3) + user message (TDD-03 Section 1.4), calls Sonnet, parses JSON response (TDD-03 Section 1.5).
- Fail-open policy (TDD-03 Section 1.6): if LLM returns malformed JSON, return `eligible: true` with a warning.
- Pydantic models: `SufficiencyResult`, `SufficiencyIssue`.

**Verify:**
- Integration test with mock Anthropic client: verify JSON parsing of a valid response.
- Unit test: malformed JSON triggers fail-open behavior (returns `eligible: true` with warning).

---

### Ticket 5.2 — Knowledge readiness scoring

**Ref:** TDD-03 Section 10

**Goal:** Create `app/agents/readiness.py` — the heuristic readiness calculator.

**Implement:**
- `compute_readiness_score(agent_id, project_id)` — synchronous DB query: 40 (has skills) + 30 (has briefing) + 20 (onboarding complete) + 10 (has learnings). (TDD-03 Section 10.1)
- `update_agent_readiness(agent_id)` — compute score and write to `agents.readiness_score`.

**Verify:**
- Unit test: agent with skills (40) + onboarding (20) = readiness 60 (partial).
- Unit test: agent with all 4 components = readiness 100 (sufficient).
- Unit test: fresh agent with nothing = readiness 0 (insufficient).

---

### Ticket 5.3 — Initial agent learning task

**Ref:** TDD-03 Section 11

**Goal:** Implement `execute_agent_learning` Celery task.

**Implement the lifecycle from TDD-03 Section 11.2:**
1. Set `agent.status = 'learning'`.
2. Build learning prompt with workspace domain context.
3. Run agent loop with tools: `web_search`, `web_browser`, `file_write`.
4. Parse output → create `agent_skills` rows with `category = 'skill'`.
5. Compute and store readiness score.
6. Set `agent.status = 'ready'`.

**Verify:**
- Integration test with mock Anthropic + mock Serper: agent produces skill entries and transitions to `ready`.

---

### Ticket 5.4 — Reflection engine

**Ref:** TDD-03 Section 9

**Goal:** Implement `execute_agent_reflection` Celery task.

**Implement:**
1. Acquire `FOR UPDATE` lock on agent row (TDD-02 Section 6.2).
2. Set `agent.status = 'reflecting'`.
3. Load recent artifacts and their contextual comments.
4. Build reflection prompt (TDD-03 Section 9.2).
5. Call Sonnet, parse JSON response (TDD-03 Section 9.3).
6. Post-processing (TDD-03 Section 9.4): insert new skills/learnings, remove obsolete entries, check token budget (trigger compaction if needed), update metadata.
7. Set `agent.status = 'ready'`, update `last_reflection_at`.

**Implement trigger check:**
- `should_trigger_reflection(agent_id)` — returns `True` if agent has ≥ 3 artifacts since last reflection OR ≥ 7 days since `last_reflection_at`.

**Verify:**
- Integration test: mock Sonnet returns insights + obsolete skills → verify new rows created, old rows deleted.
- Unit test: `FOR UPDATE` lock blocks a concurrent reflection on the same agent.

---

### Ticket 5.5 — Project briefing

**Ref:** TDD-03 Section 11.3

**Goal:** Implement `brief_all_agents(project)` — rebriefs roster agents when a project brief is published.

**Implement (TDD-03 Section 11.3 pseudocode):**
- For each active agent: delete existing `briefing` entry for this project, insert new entry with the published brief content.
- Recompute readiness scores.

**Verify:**
- Unit test: publishing a brief creates `briefing` agent_skill rows for all active agents.
- Unit test: re-publishing replaces (not stacks) existing briefing entries.

---

## Sprint 6: API Routes — Core

### Ticket 6.1 — Onboarding endpoint

**Ref:** TDD-04 Section 2

**Goal:** Implement `POST /api/onboarding`.

**Implement:**
- Validate request body (company_name, domain_description, tech_stack, team_size, use_case).
- Update workspace row with company context.
- Generate roster via Haiku LLM call (or fallback to hardcoded default roster).
- Create agent rows, each in `learning` status.
- Enqueue `execute_agent_learning` for each agent.
- Set `workspace.onboarding_completed = true`.
- Return workspace + agents array.
- Error: `409` if already onboarded.

**Verify:**
- Integration test: POST creates agents, returns 201 with correct shape.
- Integration test: second POST returns 409.

---

### Ticket 6.2 — Roster/Agent CRUD

**Ref:** TDD-04 Section 3 (16 endpoints)

**Goal:** Implement all roster endpoints.

**Implement these routes in `app/api/routes/roster.py`:**
- `GET /api/roster` — list agents with cursor pagination, status filter, include_archived.
- `GET /api/roster/{id}` — agent detail with skills summary.
- `POST /api/roster` — create agent, enqueue learning.
- `PATCH /api/roster/{id}` — update agent config.
- `DELETE /api/roster/{id}` — soft archive.
- `DELETE /api/roster/{id}/permanent` — hard delete.
- `GET /api/roster/{id}/skills` — list skills with category filter + budget info.
- `GET /api/roster/{id}/learning-profile` — readiness breakdown.
- `POST /api/roster/{id}/research` — trigger topic research.
- `POST /api/roster/{id}/reflect` — trigger reflection.
- `POST /api/roster/{id}/knowledge` — upload doc/URL to knowledge.
- `GET /api/roster/{id}/knowledge-recommendations` — list gaps.
- `POST /api/roster/{id}/knowledge-recommendations/{rid}/apply` — apply recommendation.
- `POST /api/roster/{id}/knowledge-recommendations/{rid}/dismiss` — dismiss.
- `GET /api/roster/readiness/global` — global readiness summary.

**Verify:**
- Integration test: CRUD lifecycle (create → get → update → archive → list excludes archived → permanent delete).
- Integration test: cursor pagination returns correct `next_cursor` and `has_more`.

---

### Ticket 6.3 — Project CRUD + brief management

**Ref:** TDD-04 Sections 4, 7

**Goal:** Implement project and document endpoints.

**Implement in `app/api/routes/projects.py`:**
- `GET /api/projects` — list with cursor pagination.
- `POST /api/projects` — create project.
- `PATCH /api/projects/{id}` — update.
- `DELETE /api/projects/{id}` — cascade delete (requires `X-Confirm-Delete` header).
- `GET /api/projects/{id}/context` — get brief state (draft + published).
- `PUT /api/projects/{id}/context/draft` — save working draft.
- `POST /api/projects/{id}/context/publish` — publish brief, compute fingerprint, trigger `brief_all_agents()`.

**Implement in `app/api/routes/documents.py`:**
- `GET /api/projects/{pid}/documents` — list.
- `POST /api/projects/{pid}/documents` — upload (multipart), store in S3, enqueue `process_document_upload`.
- `DELETE /api/projects/{pid}/documents/{did}` — delete chunks, S3 object, DB row.

**Verify:**
- Integration test: create project → save draft → publish → verify agents are briefed.
- Integration test: upload document → verify `processing_status` transitions from `pending` to `ready` (with mock embedding).

---

### Ticket 6.4 — Document processing pipeline

**Ref:** TDD-02 Section 2 (chunking + embedding), TDD-02 Section 3.2 (Celery task)

**Goal:** Implement `process_document_upload` Celery task.

**Implement:**
1. Download file from S3.
2. Extract text: PDF via `pymupdf`, DOCX via `python-docx`, plain text as-is.
3. Chunk text: 512-token chunks, 50-token overlap.
4. Compute embeddings via embedding API (configurable — Voyage or placeholder).
5. Insert `document_chunks` rows with pgvector embeddings.
6. Update `document.chunk_count`, `document.processing_status = 'ready'`.

**Verify:**
- Integration test: upload a small text file → verify chunks are created with correct count.
- Integration test: upload a PDF → verify text extraction works.

---

### Ticket 6.5 — Artifact lifecycle endpoints

**Ref:** TDD-04 Section 5

**Goal:** Implement the complete artifact API.

**Implement in `app/api/routes/artifacts.py`:**
- `POST /api/artifacts` — create artifact from brief (does NOT trigger execution).
- `POST /api/artifacts/{id}/validate` — run sufficiency check (from Ticket 5.1).
- `POST /api/artifacts/{id}/delegate` — preview mode (`confirm: false`) returns plan; confirm mode (`confirm: true`) creates execution_wave and enqueues `execute_artifact_dag`.
- `GET /api/artifacts/{id}` — artifact detail.
- `GET /api/artifacts/{id}/status` — lightweight heartbeat endpoint.
- `GET /api/artifacts/{id}/versions` — list all versions.
- `GET /api/artifacts/{id}/versions/{v}/files/{path:path}` — proxy file from S3 (AD-15).
- `POST /api/artifacts/{id}/iterate` — create contextual comment + execution wave.
- `PATCH /api/artifacts/{id}/approve` — approve, trigger reflection check.
- `PATCH /api/artifacts/{id}/cancel` — cancel, revoke active Celery task if drafting.
- `GET /api/projects/{pid}/artifacts` — list artifacts in project with status filter.
- `POST /api/briefs/sufficiency-check` — standalone validation (no artifact required).

**Verify:**
- Integration test: full lifecycle — create → validate → delegate (preview) → delegate (confirm) → poll status → check versions → approve.
- Integration test: iterate creates a new execution wave and contextual comment.
- Integration test: cancel revokes execution and sets status.
- Integration test: file proxy returns correct content-type and body from S3.

---

## Sprint 7: API Routes — Integrations

### Ticket 7.1 — Git provider connections + push flow

**Ref:** TDD-04 Sections 8, 9

**Goal:** Implement Git provider CRUD and the code artifact push flow.

**Implement in `app/api/routes/git_providers.py`:**
- `GET /api/git-providers/connections` — list.
- `POST /api/git-providers/connections` — create with PAT validation.
- `POST /api/git-providers/connections/{id}/test` — test connection.
- `GET /api/git-providers/connections/{id}/repos` — list repos.
- `POST /api/git-providers/connections/{id}/repos/{owner}/{repo}/webhook` — auto-configure webhook (AD-17).
- `DELETE /api/git-providers/connections/{id}` — delete + remove webhooks.

**Implement in `app/core/git_push.py`:**
- `push_artifact_to_git(artifact, version)` — the push flow from TDD-04 Section 9.1: clone base branch, create feature branch, write files, commit, push, create PR, store PR URL/number on artifact.
- `push_iteration_to_git(artifact, version)` — iteration push (TDD-04 Section 9.2): checkout existing branch, write updated files, commit, push.

**Wire into `execute_artifact_dag`:** After finalize step, if `artifact_type == "code"`, call `push_artifact_to_git()` (or `push_iteration_to_git()` for iterations).

**Verify:**
- Integration test: create connection with valid PAT → verify repos are listed.
- Integration test (with mock git): push flow creates PR and stores URL on artifact.

---

### Ticket 7.2 — Webhook receiver

**Ref:** TDD-04 Section 10

**Goal:** Implement GitHub and GitLab webhook endpoints.

**Implement in `app/api/routes/webhooks.py`:**
- `POST /api/webhooks/github` — verify `X-Hub-Signature-256`, handle events:
  - `pull_request_review_comment` → create contextual comment + trigger iteration.
  - `pull_request_review` (changes_requested) → same.
  - `pull_request` (closed + merged) → approve artifact.
  - `pull_request` (closed + not merged) → no action.
- `POST /api/webhooks/gitlab` — verify `X-Gitlab-Token`, handle equivalent events.
- Always return `200` (even on internal errors — log instead).
- Deduplicate via `external_comment_id` unique constraint.

**Verify:**
- Unit test: valid signature passes, invalid signature returns 401.
- Integration test: mock `pull_request_review_comment` event → verify contextual comment created + iteration wave enqueued.
- Integration test: mock `pull_request` merged event → verify artifact status transitions to `approved`.

---

### Ticket 7.3 — MCP connections

**Ref:** TDD-04 Section 11

**Goal:** Implement MCP connection endpoints.

**Implement in `app/api/routes/mcp.py`:**
- `GET /api/mcp/connections` — list.
- `POST /api/mcp/connections` — create, encrypt auth, discover tools.
- `POST /api/mcp/connections/{id}/test` — ping server.
- `POST /api/mcp/connections/{id}/discover-tools` — re-discover.
- `DELETE /api/mcp/connections/{id}` — delete.

**Verify:**
- Integration test with mock MCP server: create connection → verify tools discovered and stored.

---

### Ticket 7.4 — Usage & cost tracking

**Ref:** TDD-04 Section 12

**Goal:** Implement usage endpoints.

**Implement in `app/api/routes/usage.py`:**
- `GET /api/usage` — aggregate stats from `execution_waves` and `artifact_versions`. Supports `period` param (day/week/month).
- `PATCH /api/usage/budget` — update monthly budget ceiling.

**Verify:**
- Integration test: create some execution waves with costs → verify aggregation is correct.

---

### Ticket 7.5 — WebSocket endpoint + event system

**Ref:** TDD-05 Section 6

**Goal:** Implement the WebSocket endpoint and event broadcasting.

**Implement:**
- `WS /ws` — WebSocket connection endpoint. Manages connected clients.
- `broadcast_event(event_type, payload)` — sends to all connected clients.
- Integrate into key state transitions:
  - After `execute_artifact_dag` completes → broadcast `artifact.status_changed`.
  - After agent status changes → broadcast `agent.status_changed`.
  - After wave completes → broadcast `execution.wave_completed`.
  - After execution fails → broadcast `execution.failed`.
  - After cost check shows ≥ 90% usage → broadcast `budget.warning`.

**Verify:**
- Integration test: connect a WebSocket client, trigger an artifact status change, verify event received.

---

### Ticket 7.6 — Health endpoint

**Ref:** TDD-04 Section 13

**Goal:** Implement `GET /health`.

- Check: PostgreSQL connection, Redis ping, MinIO bucket exists.
- Return `200` with service status or `503` if any service is down.

**Verify:**
- Integration test: all services up → `200`. Stop Redis → `503`.

---

## Sprint 8: Frontend — Scaffold

### Ticket 8.1 — Initialize Next.js project

**Ref:** TDD-05 Section 1

**Goal:** Create the Next.js 15 application in `frontend/`.

**Steps:**
1. `pnpm create next-app frontend` with TypeScript, Tailwind CSS v4, App Router, src directory disabled.
2. Install dependencies: `@tanstack/react-query`, `zustand`, `react-hook-form`, `@hookform/resolvers`, `zod`, `lucide-react`, `date-fns`, `react-diff-viewer-continued`, `react-markdown`, `remark-gfm`, `sonner`.
3. Initialize shadcn/ui: `pnpm dlx shadcn@latest init`.
4. Configure Next.js: API rewrites to `http://localhost:8000` in dev.
5. Configure ESLint + Prettier.

**Verify:**
- `pnpm dev` starts at `http://localhost:3000` and renders a page.
- `pnpm build` succeeds with no TypeScript errors.

---

### Ticket 8.2 — Design system tokens

**Ref:** TDD-05 Section 2

**Goal:** Implement the color tokens, typography, and dark mode infrastructure.

**Steps:**
1. Create `app/tokens.css` with all CSS custom properties from TDD-05 Section 2.2 (light + dark).
2. Import Inter and JetBrains Mono fonts.
3. Configure Tailwind to use CSS variables.
4. Implement `lib/theme.ts` with `getInitialTheme()` and `applyTheme()` (TDD-05 Section 2.5).
5. Add shadcn/ui components: `button`, `card`, `dialog`, `input`, `textarea`, `badge`, `tabs`, `tooltip`, `skeleton`, `progress`, `separator`, `dropdown-menu`.

**Verify:**
- Toggle between light and dark mode — colors switch correctly.
- shadcn/ui components render with the custom tokens.

---

### Ticket 8.3 — App shell and providers

**Ref:** TDD-05 Sections 3, 4, 6

**Goal:** Build the root layout, providers, and sidebar.

**Implement:**
- `app/layout.tsx` — root layout with `ThemeProvider`, `QueryClientProvider`, `WebSocketProvider`, sidebar + main area (TDD-05 Section 3.2).
- `providers/query-provider.tsx` — TanStack Query client with default stale times from TDD-05 Section 4.1.
- `providers/websocket-provider.tsx` — WebSocket connection with reconnect, query invalidation bridge (TDD-05 Section 6.3).
- `stores/ui-store.ts` — Zustand store for sidebar, theme, diff mode, modals (TDD-05 Section 4.2).
- `components/layout/sidebar.tsx` — Projects, Agency Roster, Settings links. Global readiness indicator.
- `components/notifications/notification-toast.tsx` — Sonner integration.

**Verify:**
- App renders with sidebar and main content area.
- Sidebar navigation works (links render, active state highlights).
- Dark mode toggle persists across page loads.

---

### Ticket 8.4 — API client + query keys

**Ref:** TDD-05 Sections 4.1, 5

**Goal:** Build the typed API client and TanStack Query key system.

**Implement:**
- `lib/api-client.ts` — base `request()` function with error handling and `ApiError` class (TDD-05 Section 5.1).
- `lib/api/index.ts` — all API methods organized by domain (TDD-05 Section 5.2).
- `lib/query-keys.ts` — complete query key factory (TDD-05 Section 4.1).

**Verify:**
- Unit test: `ApiError` serializes correctly.
- TypeScript compilation succeeds with all API methods.

---

## Sprint 9: Frontend — Core Flows

### Ticket 9.1 — Onboarding flow

**Ref:** TDD-05 Section 13, TDD-01 Journey J1

**Goal:** Build the onboarding wizard at `/onboarding`.

**Implement:**
- `app/onboarding/page.tsx` — multi-step form.
- `features/onboarding/onboarding-form.tsx` — company context form (Step 1).
- `features/onboarding/roster-preview.tsx` — generated roster with inline editing (Step 2).
- Root page redirect guard: check if onboarded, redirect accordingly (TDD-05 Section 13.2).

**Verify:**
- Manual test: complete onboarding → agents created → redirected to dashboard.

---

### Ticket 9.2 — Project management

**Ref:** TDD-05 Section 15, TDD-01 Journey J5

**Goal:** Build project list, create, detail, brief editor, and document manager.

**Implement:**
- `app/projects/page.tsx` — project grid with "New Project" dialog.
- `app/projects/[projectId]/page.tsx` — artifact list tab.
- `app/projects/[projectId]/brief/page.tsx` — brief editor with auto-save (debounced 1s) + publish.
- `app/projects/[projectId]/documents/page.tsx` — drag-and-drop upload + document list.
- `features/projects/` — all subcomponents (project-card, create-dialog, brief-editor, document-manager).
- `components/shared/cursor-pagination.tsx` — "Load More" button for paginated lists.

**Verify:**
- Manual test: create project → edit brief → publish → upload document.

---

### Ticket 9.3 — Smart Brief form + delegation

**Ref:** TDD-05 Sections 8, TDD-01 Journey J2/J3

**Goal:** Build the artifact creation flow — the single most important UI.

**Implement:**
- `app/projects/[projectId]/artifacts/new/page.tsx` — Smart Brief page.
- `features/artifacts/smart-brief-form.tsx` — form with React Hook Form + Zod schema (TDD-05 Section 8.2).
- `features/artifacts/sufficiency-feedback.tsx` — inline issue display with `matched_text` highlighting (TDD-05 Section 8.3).
- `features/artifacts/delegate-preview.tsx` — modal showing plan, team, cost, override controls (TDD-05 Section 8.4).

**Verify:**
- Manual test: fill form → validate (see issues inline) → fix → delegate → see preview → confirm.

---

### Ticket 9.4 — Heartbeat UI

**Ref:** TDD-05 Section 9, TDD-01 Journey J2 Step 8

**Goal:** Build the execution progress panel.

**Implement:**
- `features/artifacts/heartbeat-panel.tsx` — step indicators, progress bar, cost counter, cancel button (TDD-05 Section 9.2-9.3).
- Conditional 3s polling via TanStack Query `refetchInterval` (TDD-05 Section 4.1).
- Transition: when status changes from `drafting`, fade out heartbeat and load review UI.

**Verify:**
- Manual test: delegate an artifact → see heartbeat steps progress → see completion transition.

---

### Ticket 9.5 — Artifact review (prose + code)

**Ref:** TDD-05 Sections 10, 11, 12, TDD-01 Journeys J2/J3

**Goal:** Build the review UI — the second most important UI.

**Implement:**
- `app/projects/[projectId]/artifacts/[artifactId]/page.tsx` — routes to heartbeat or review based on status.
- `features/artifacts/artifact-review.tsx` — shell that routes to prose or code review.
- `features/artifacts/prose-viewer.tsx` — markdown rendering via `react-markdown` + `remark-gfm`.
- `features/artifacts/review-sidebar.tsx` — sources, assumptions, cost, comments.
- `features/artifacts/version-switcher.tsx` — version tabs/dropdown.
- `features/artifacts/artifact-actions.tsx` — Approve + Cancel buttons with optimistic updates.
- `features/artifacts/code-artifact-review.tsx` — PR link, file list, optional feedback form (TDD-05 Section 10.3).

**Verify:**
- Manual test: review a prose artifact → see rendered content + sidebar.
- Manual test: review a code artifact → see PR link prominently.

---

### Ticket 9.6 — Diff viewer + contextual commenting

**Ref:** TDD-05 Sections 11, 12

**Goal:** Complete the review experience with diffs and inline feedback.

**Implement:**
- `features/artifacts/prose-diff-viewer.tsx` — `react-diff-viewer-continued` with custom theme tokens, unified/side-by-side toggle (TDD-05 Section 11.3-11.4). Lazy-loaded.
- `stores/selection-store.ts` — Zustand store for text selection state (TDD-05 Section 4.2).
- `hooks/use-text-selection.ts` — native `Selection` API hook (TDD-05 Section 12.1).
- `features/comments/floating-comment-toolbar.tsx` — positioned above selection, "Comment" button (TDD-05 Section 12.2).
- `features/comments/comment-form.tsx` — instruction input, submit calls `POST /api/artifacts/{id}/iterate`.
- `features/comments/comment-thread.tsx` — list of comments in sidebar.

**Verify:**
- Manual test: view diff between v1 and v2 in both modes.
- Manual test: select text → floating toolbar appears → submit comment → artifact transitions to heartbeat.

---

## Sprint 10: Frontend — Settings & Polish

### Ticket 10.1 — Roster management UI

**Ref:** TDD-05 Section 14, TDD-01 Journey J4

**Goal:** Build the roster overview and agent detail pages.

**Implement:**
- `app/roster/page.tsx` — agent grid with status filter pills.
- `features/roster/agent-card.tsx` — name, specialization, status, progression, readiness bar.
- `app/roster/[agentId]/page.tsx` — agent detail with tabs (Profile, Skills, History, Knowledge).
- `features/roster/agent-skills-list.tsx` — skill entries with token budget indicator.
- `features/roster/knowledge-recommendations.tsx` — apply/dismiss actions.
- `features/roster/research-dialog.tsx` — manual research trigger.

**Verify:**
- Manual test: view roster → click agent → see profile → view skills → trigger research.

---

### Ticket 10.2 — Settings pages

**Ref:** TDD-05 Section 16, TDD-01 Journey J6

**Goal:** Build all settings pages.

**Implement:**
- `app/settings/git/page.tsx` — Git provider connections (TDD-05 Section 16.1).
- `app/settings/mcp/page.tsx` — MCP connections (TDD-05 Section 16.2).
- `app/settings/usage/page.tsx` — usage dashboard with budget editor (TDD-05 Section 16.3).
- Shared: connection cards, test buttons, confirmation dialogs for delete.

**Verify:**
- Manual test: connect GitHub → list repos → configure webhook.
- Manual test: view usage breakdown → edit budget.

---

### Ticket 10.3 — Error handling, loading states, responsive design

**Ref:** TDD-05 Sections 17, 18, 19

**Goal:** Polish the entire UI.

**Implement:**
- Skeleton loaders for all data-fetching components (TDD-05 Section 17.1).
- Error boundaries with retry buttons (TDD-05 Section 17.2).
- Optimistic updates for approve/cancel/archive (TDD-05 Section 17.3).
- Responsive layout: sidebar collapse, review sidebar stacking, diff mode restriction (TDD-05 Section 18.2).
- Accessibility: keyboard navigation, `aria-live` regions, focus management, reduced motion (TDD-05 Section 19).

**Verify:**
- Resize browser → sidebar collapses → content fills width.
- Navigate entire app using only keyboard.
- Check with screen reader: status changes announced, modals trap focus.

---

## Sprint 11: Integration & QA

### Ticket 11.1 — End-to-end: Prose artifact flow

**Goal:** Verify the complete prose artifact journey with all services running.

**Test scenario (TDD-01 Journey J2):**
1. Complete onboarding → agents reach `ready`.
2. Create project → publish brief → agents are rebriefed.
3. Create prose artifact → validate → fix issues → delegate.
4. Watch heartbeat UI progress through waves.
5. Artifact transitions to `in_review` → review content + sidebar.
6. Highlight text → submit comment → iteration executes.
7. View v2 diff → approve.
8. Verify agents enter reflection if threshold met.

**Verify:** Every state transition is correct. Every UI element renders. Cost tracking is accurate.

---

### Ticket 11.2 — End-to-end: Code artifact flow

**Goal:** Verify the complete code artifact journey.

**Test scenario (TDD-01 Journey J3):**
1. Connect GitHub (PAT) → configure webhook.
2. Create code artifact → delegate.
3. Execution completes → PR is opened on GitHub.
4. Review screen shows PR link.
5. Simulate webhook: PR comment → iteration triggers → new commit pushed.
6. Simulate webhook: PR merged → artifact approved.

**Verify:** PR is created correctly. Webhook iteration works. Merge detection works.

---

### Ticket 11.3 — Edge case testing

**Goal:** Verify all edge cases from TDD-01 Section 6.

**Test scenarios:**
- Brief validation failure → issues displayed inline (6.1).
- Agent fails mid-execution → retry 3x → error banner (6.2).
- Execution timeout → reaper catches orphaned wave (6.2).
- Cost ceiling hit mid-execution → execution aborts cleanly (6.3).
- Monthly budget exceeded → new executions blocked (6.3).
- Agent not ready → excluded from auto-assembly with warning (6.5).
- Two artifacts use same agent simultaneously → both execute independently (6.6).
- Two agents reflect simultaneously → second blocks until first commits (6.6).
- Webhook with invalid signature → rejected (6.7).
- Webhook for unknown PR → ignored (6.7).
- Webhook for already-approved artifact → ignored (6.7).

**Verify:** Each scenario produces the correct system behavior per TDD-01.

---

### Ticket 11.4 — Performance baseline

**Goal:** Establish performance baselines.

**Measure:**
- Sufficiency check latency (target: < 4s per TDD-03 Section 1.2).
- Router call latency (target: < 2s per TDD-03 Section 3.1).
- Heartbeat polling endpoint response time (target: < 50ms).
- Frontend initial load (target: < 1.5s FCP, < 3s TTI per TDD-05 Section 20).
- Frontend bundle size (target: < 150 KB gzipped initial).

**Verify:** All targets met. Document any that miss for optimization in a follow-up.

---

## Dependency Graph

```
Sprint 0: Project Scaffold
  └── 0.1 Project scaffold + Docker + dependencies
        │
Sprint 1: Database ─────────────────────────────────────┐
  ├── 1.1 SQLAlchemy models                              │
  └── 1.2 Alembic migrations                             │
        │                                                │
Sprint 2: Core Services                                  │
  ├── 2.1 S3 workspace                                   │
  ├── 2.2 Cost calculation                               │
  ├── 2.3 Celery tasks (stubs)                           │
  └── 2.4 Shared utilities                               │
        │                                                │
Sprint 3: AI Foundation                                  │
  ├── 3.1 Agent execution loop                           │
  ├── 3.2 Tool definitions                               │
  ├── 3.3 Prompt assembly                                │
  ├── 3.4 Agent memory loader                            │
  └── 3.5 Upstream context builder                       │
        │                                                │
Sprint 4: DAG & Orchestration                            │
  ├── 4.1 DAG template library                           │
  ├── 4.2 Auto-assembly + router                         │
  ├── 4.3 execute_artifact_dag ◄── (the core task)       │
  └── 4.4 Reaper + monthly reset                         │
        │                                                │
Sprint 5: Sufficiency, Memory, Reflection                │
  ├── 5.1 Sufficiency check                              │
  ├── 5.2 Knowledge readiness                            │
  ├── 5.3 Agent learning task                            │
  ├── 5.4 Reflection engine                              │
  └── 5.5 Project briefing                               │
        │                                                │
Sprint 6: API Routes — Core                              │
  ├── 6.1 Onboarding                                     │
  ├── 6.2 Roster CRUD (16 endpoints)                     │
  ├── 6.3 Projects + documents                           │
  ├── 6.4 Document processing pipeline                   │
  └── 6.5 Artifact lifecycle (12 endpoints)              │
        │                                                │
Sprint 7: API Routes — Integrations                      │
  ├── 7.1 Git providers + push flow                      │
  ├── 7.2 Webhook receiver                               │
  ├── 7.3 MCP connections                                │
  ├── 7.4 Usage tracking                                 │
  ├── 7.5 WebSocket events                               │
  └── 7.6 Health endpoint                                │
        │                                                │
        │    ┌───────────────────────────────────────────┘
        │    │ (Frontend can start here — Sprint 8)
        ▼    ▼
Sprint 8: Frontend Scaffold ◄── (parallelizable with Sprint 6+)
  ├── 8.1 Next.js init
  ├── 8.2 Design system tokens
  ├── 8.3 App shell + providers
  └── 8.4 API client + query keys
        │
Sprint 9: Frontend — Core Flows
  ├── 9.1 Onboarding
  ├── 9.2 Project management
  ├── 9.3 Smart Brief + delegation
  ├── 9.4 Heartbeat UI
  ├── 9.5 Artifact review (prose + code)
  └── 9.6 Diff viewer + contextual comments
        │
Sprint 10: Frontend — Settings & Polish
  ├── 10.1 Roster management
  ├── 10.2 Settings pages
  └── 10.3 Error handling + responsive + a11y
        │
Sprint 11: Integration & QA
  ├── 11.1 E2E: Prose artifact flow
  ├── 11.2 E2E: Code artifact flow
  ├── 11.3 Edge case testing
  └── 11.4 Performance baseline
```

**Parallelization note:** Sprint 8 (frontend scaffold) can start as soon as the API contracts from TDD-04 are finalized — it doesn't need the backend to be complete. Sprints 8-10 can overlap with Sprints 6-7 if two developers are working in parallel.

---

## Ticket Count Summary

| Sprint | Tickets | Description |
|---|---|---|
| 0 | 3 | Infrastructure & clean slate |
| 1 | 2 | Database schema |
| 2 | 4 | Core backend services |
| 3 | 5 | AI engine foundation |
| 4 | 4 | DAG & orchestration |
| 5 | 5 | Sufficiency, memory, reflection |
| 6 | 5 | API routes — core |
| 7 | 6 | API routes — integrations |
| 8 | 4 | Frontend scaffold |
| 9 | 6 | Frontend core flows |
| 10 | 3 | Frontend settings & polish |
| 11 | 4 | Integration & QA |
| **Total** | **51** | |
