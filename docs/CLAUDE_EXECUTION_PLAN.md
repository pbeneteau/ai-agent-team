# CLAUDE_EXECUTION_PLAN.md
**Project:** Migration to Vision 2.0 (Artifact-First Orchestrator)
**Role:** Claude Code is the Junior Developer. The Human is the Tech Lead.
**Rules for Claude:** 
1. Do NOT execute multiple phases at once. 
2. Only modify the files explicitly mentioned or strictly related to the current phase.
3. Run `pytest` (if available) or `fastapi dev` to ensure the app compiles after your changes.

---

## Phase 1: The Great Deletion (Removing V1 Bloat)
**Goal:** Strip out the legacy "Jira for Bots" and "Chatbot" logic to create a clean slate.

**Claude Code Prompt:**
> "Read `VISION_2.0.md`. We are executing Phase 1. I need you to safely delete the following legacy features:
> 1. Delete all WebSocket endpoints and chat logic (look in `app/api/routes/chat.py` and `app/api/routes/task_chat.py`).
> 2. Delete the Organigramme API from `app/api/routes/teams.py`.
> 3. In `app/models/task.py` and `app/core/orchestrator.py`, remove the 9-state Kanban logic (`triage`, `backlog`, `queued`, `planning`, `input_needed`, `partial`). 
> 4. Clean up any unused imports caused by these deletions. Ensure the FastAPI app still starts without syntax errors."

**Human Action:** Review changes. Run `git commit -am "chore: phase 1 - delete legacy chat and kanban state machine"`.

---

## Phase 2: Infrastructure as Code
**Goal:** Set up the local Docker environment for Postgres, Redis, and MinIO (S3).

**Claude Code Prompt:**
> "We are executing Phase 2. Create a `docker-compose.yml` file in the root directory. It must provision:
> 1. A PostgreSQL 16 database with the `pgvector` extension.
> 2. A Redis container (for Celery and PubSub).
> 3. A MinIO container (to simulate S3 for our stateless workspaces).
> Also, update `.env.example` with the necessary environment variables to connect to these three services locally."

**Human Action:** Run `docker-compose up -d`. Copy `.env.example` to `.env`. Run `git commit -am "chore: phase 2 - add docker-compose infra"`.

---

## Phase 3: Data Model Rewrite (SQLAlchemy)
**Goal:** Replace JSON file persistence with a relational database.

**Claude Code Prompt:**
> "We are executing Phase 3. We are replacing JSON file persistence with SQLAlchemy (asyncpg). 
> 1. Create `app/core/database.py` to handle the async database connection and session maker.
> 2. Create new SQLAlchemy declarative models in `app/models/domain.py`:
>    - `Project`: id, name, description, created_at.
>    - `Artifact`: id, project_id, title, goal, status (Enum: Drafting, In Review, Approved).
>    - `ArtifactVersion`: id, artifact_id, version_number (int), s3_file_path, token_cost, created_at.
>    - `ContextualComment`: id, artifact_version_id, highlighted_text, instruction, resolved.
> 3. Write a simple script or Alembic migration to create these tables. Do not touch the orchestrator yet."

**Human Action:** Verify the tables are created in your local Postgres DB. Run `git commit -am "feat: phase 3 - sqlalchemy data models"`. Type `/compact` in Claude Code to clear its memory.

---

## Phase 4: Stateless Workspaces & Diff Engine
**Goal:** Move file generation to S3 and implement version diffing.

**Claude Code Prompt:**
> "We are executing Phase 4. We need to make agent workspaces stateless.
> 1. Create `app/core/s3_workspace.py` using `aioboto3` or `boto3`.
> 2. Implement a class `S3WorkspaceManager` with methods: `upload_artifact_version(content, artifact_id, version)`, `download_artifact_version(s3_path)`, and `get_artifact_diff(old_s3_path, new_s3_path)`.
> 3. Use Python's built-in `difflib` to generate a unified diff string in `get_artifact_diff`.
> 4. Ensure it reads credentials from the MinIO env vars we set up in Phase 2."

**Human Action:** Review the S3 logic. Run `git commit -am "feat: phase 4 - s3 workspace and diff engine"`.

---

## Phase 5: The Smart Brief Engine
**Goal:** Refactor the sufficiency check to power the frontend's real-time form validation.

**Claude Code Prompt:**
> "We are executing Phase 5. Refactor `app/core/task_sufficiency.py`. 
> 1. Update the LLM system prompt so it strictly returns a JSON array of objects with this schema: `{"highlight_quote": "exact text from user input", "issue": "Why it is vague", "suggestion": "How to fix it"}`.
> 2. Update the FastAPI route `POST /api/tasks/sufficiency-check` (rename it to `/api/artifacts/sufficiency-check`) to accept a title and description, and return this exact JSON schema.
> 3. Ensure the endpoint is optimized for speed (e.g., using a smaller/faster model tier if possible)."

**Human Action:** Test the endpoint via Swagger UI (`http://localhost:8000/docs`). Run `git commit -am "feat: phase 5 - smart brief sufficiency engine"`.

---

## Phase 6: Durable Execution (Celery) & Auto-Assume
**Goal:** Replace `asyncio.gather` with Celery and remove `input_needed` deadlocks.

**Claude Code Prompt:**
> "We are executing Phase 6. We are replacing `asyncio.gather` with Celery.
> 1. Create `app/core/celery_app.py` configuring Celery with our Redis broker.
> 2. Refactor `app/core/orchestrator.py`. Create a Celery task called `generate_artifact`. 
> 3. The task should: Take an `artifact_id`, run the LLM agent pipeline, save the resulting markdown/code to S3 using `S3WorkspaceManager`, create an `ArtifactVersion` in Postgres, and update the `Artifact` status to 'In Review'.
> 4. CRITICAL: Implement the 'Auto-Assume' rule. If an agent gets stuck, it must NOT pause. It must append a warning block `[⚠️ ASSUMPTION MADE: ...]` to the document and finish the execution. Remove all logic related to pausing for human input."

**Human Action:** Start the Celery worker locally (`celery -A app.core.celery_app worker`). Run `git commit -am "feat: phase 6 - celery execution and auto-assume"`. Type `/compact` in Claude Code.

---

## Phase 7: The New API Layer
**Goal:** Expose the new Artifact and Iteration endpoints for the frontend.

**Claude Code Prompt:**
> "We are executing Phase 7. Wire up the final REST APIs in `app/api/routes/artifacts.py`. I need the following endpoints:
> 1. `POST /api/artifacts/` (Creates the Artifact and triggers the Celery task).
> 2. `GET /api/artifacts/{id}` (Returns the Artifact and its Versions).
> 3. `GET /api/artifacts/{id}/diff?v1=1&v2=2` (Returns the diff using `S3WorkspaceManager`).
> 4. `POST /api/artifacts/{id}/iterate` (Accepts a `ContextualComment`, creates it in the DB, and triggers a new Celery task to generate the next version).
> 5. Clean up and delete the old `tasks.py` router completely."

**Human Action:** Test the full flow via Swagger UI. Run `git commit -am "feat: phase 7 - artifact api layer"`. 