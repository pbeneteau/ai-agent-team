# Project Brief For Coding Agents

## Project In 30 Seconds

This is a local-first AI agent team orchestrator. A top-level agent named Alex helps the user create teams, plan work, and launch tasks. Teams contain leads and specialists. Tasks are executed with explicit execution plans, progress logs, deliverables, and reliability metadata.

The product is not a generic chatbot. Its value is:

- specialized agents with scoped context
- observable task execution
- explicit planning before risky execution
- local persistence
- evidence-oriented outputs instead of vague LLM summaries

## Current Product Priorities

- keep universal plan mode safe
- keep task orchestration explicit and inspectable
- improve agent reliability and evidence handling
- preserve a good local UX
- keep deliverables and markdown-rich outputs usable
- preserve structured-output observability across backend and chat flows
- keep team creation and agent learning aligned across all entry points

## Core Backend Concepts

### Alex chat and plan mode

- `backend/app/api/routes/chat.py`
- Alex can answer directly, ask for info, enter plan mode, or trigger learning.
- Plan mode now follows a guarded workflow:
  - discovery
  - draft with structured validation metadata
  - clarification if blockers exist
  - explicit confirmation
  - single execution
- Drafts expose typed validation fields such as:
  - `validation_issues`
  - `validation_status`
  - `execution_eligibility`
- Confirmation must stay backend-authoritative. The frontend should not optimistically treat a draft as executable.

### Universal plan state

- `backend/app/core/universal_plan.py`
- Tracks session, draft, revision, blockers, validation, eligibility, and execution/completion state.
- Validates task/team drafts before execution.
- Must support clarification loops and drift-safe revalidation before execution.

### Task orchestration

- `backend/app/core/orchestrator.py`
- This is the canonical task engine.
- Tasks expose:
  - `execution_mode`
  - `execution_plan`
  - `progress_log`
  - `deliverables`
  - `sources`
  - `assumptions`
  - `warnings`
- Tasks also carry execution eligibility metadata and should be blocked early when not executable.

Do not regress this into a hidden or implicit flow.

### Agents and teams

- `backend/app/core/agent_factory.py`
- Agents and teams are stored locally.
- Team lead resolution and model tier handling are important.
- Runtime recovery on restart exists and should not be broken.
- Newly created teams and agents must consistently trigger learning across all creation paths.

### Learning and research

- `backend/app/core/learning.py`
- Handles learning passes, briefing, rebriefing, and research-oriented enrichment.
- Agents that remain `pending` are not ready for work until learning has run successfully.

### Structured outputs and usage telemetry

- `backend/app/core/structured_json.py`
- `backend/app/core/usage_tracker.py`
- Native structured output, text JSON fallback, repair paths, and observability are all intentional product behaviors.
- Backend flows expose real structured generation channels such as:
  - `native_json_schema`
  - `heuristic_fallback`
  - `tool_use`
  - `text_json`
  - `text_json_repair`

## Core Frontend Concepts

### Chat UI

- `frontend/components/chat/ChatPanel.tsx`
- Main Alex shell.
- Plan mode UI is split into reusable subcomponents under `frontend/components/chat/`.
- The plan review UI reflects backend validation state, not just freeform prose.

### Task result UI

- `frontend/components/tasks/TaskCard.tsx`
- Rich task dialog with:
  - result rendering
  - execution plan visibility
  - progress timeline
  - deliverables browser
  - retry flow

### Agent workspace UI

- `frontend/components/agents/WorkspacePanel.tsx`
- Lets the user view/edit skills, manage knowledge, browse files.
- Long content rendering and scrolling behavior are sensitive here.

### Project context and recommendations UI

- `frontend/components/project-context/ProjectContextHub.tsx`
- This surface exposes:
  - project context editing
  - team recommendations
  - team change recommendations
  - global knowledge readiness
  - structured generation channel badges

### Usage UI

- `frontend/app/usage/page.tsx`
- This page is not just cost reporting. It is also the main UI for structured-output observability by flow.

## Real Local State

This repo often runs with meaningful local state already present.

Important files:

- `backend/data/agents.json`
- `backend/data/teams.json`
- `backend/data/workspaces/`
- `backend/data/task_deliverables/`
- `backend/data/documents/`
- `backend/data/knowledge_readiness/`
- `backend/data/usage.json`

Be careful with changes that write, delete, migrate, or reset local data.

## High-Risk Files

- `backend/app/api/routes/chat.py`
- `backend/app/api/routes/teams.py`
- `backend/app/core/universal_plan.py`
- `backend/app/core/orchestrator.py`
- `backend/app/core/structured_json.py`
- `backend/app/core/agent_factory.py`
- `frontend/components/chat/ChatPanel.tsx`
- `frontend/components/chat/PlanReviewCard.tsx`
- `frontend/components/tasks/TaskCard.tsx`
- `frontend/components/agents/WorkspacePanel.tsx`

## Things To Preserve

- explicit confirmation before executing planned actions
- blockers that truly block
- idempotent or safe plan execution
- clarification loops that return to review instead of failing generically
- task-linked deliverables
- markdown rendered as markdown
- visible user feedback for failures
- names/labels instead of raw ids when possible
- configurable model tiers instead of hardcoded model names
- structured generation channel visibility in usage and relevant UI surfaces
- automatic learning after team creation
- restart recovery without silent data loss

## Things To Avoid

- giant implicit context blobs
- tiny unreadable modals
- silent failures
- backend/frontend contract drift
- hardcoded one-off logic when a typed model/state already exists
- assumptions that local state is clean
- bypassing plan eligibility guards
- reintroducing text-only plan blockers as the source of truth
- breaking cache invalidation or observability around recommendations/readiness

## Validation Commands

Frontend:

```bash
cd frontend
npm run test
npm run build
```

Backend:

```bash
python3 -m pytest backend/tests/test_universal_plan.py
python3 -m pytest backend/tests/test_task_orchestration.py
python3 -m pytest backend/tests/test_structured_json.py
python3 -m pytest backend/tests/test_knowledge_recommendations.py
python3 -m pytest backend/tests/test_smoke.py
```

## Recommended Working Pattern For Another LLM

1. Read `AGENTS.md`.
2. Read this file.
3. Read only the directly affected files.
4. If changing an API/model, read the matching consumer on the other side.
5. If changing a structured-output flow, inspect both the runtime and the observability surface.
6. Validate the narrowest relevant path before finishing.
