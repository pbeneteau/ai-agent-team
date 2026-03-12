# AGENTS.md

## Fast Start

This repo is a local-first AI agent orchestration product for one user.

Before broad work, read:

1. `docs/llm/PROJECT_BRIEF.md`
2. the file you are changing
3. related API/types on the other side of the contract if the change crosses backend/frontend

If `README.md` and code diverge, trust the code.

## What This Product Is

- Alex is the top-level associate.
- Teams and agents are persisted locally.
- Tasks use explicit execution plans, progress logs, and deliverables.
- Universal plan mode exists to avoid executing task/team creation too early.
- The product is designed to improve reliability and reduce hallucinated agent output.

## Non-Goals

- Do not optimize for multi-user, auth, tenancy, or cloud-scale architecture unless the user explicitly asks.
- Do not replace explicit plan/execution state with hidden implicit behavior.

## Core Invariants

- A plan proposed by Alex must not execute before explicit confirmation.
- `plan_confirm`, `plan_cancel`, and `plan_revise` stay tied to `session_id` and `draft_id`.
- Blocking questions must really block execution.
- Tasks keep `execution_mode`, `execution_plan`, `progress_log`, and deliverables.
- Deliverables remain task-linked and browsable/downloadable.
- Markdown content should render as Markdown in the UI, not raw text.
- Changes to local JSON/file persistence are risky and must preserve recovery behavior.
- Evidence, warnings, and assumptions are first-class; do not hide uncertainty.

## Where Things Live

- `backend/app/api/routes/chat.py`: Alex chat WS, plan mode, learning triggers
- `backend/app/core/universal_plan.py`: plan session, validation, executors
- `backend/app/core/orchestrator.py`: task orchestration, execution plan, deliverables
- `backend/app/core/agent_factory.py`: teams, agents, model tiers, runtime recovery
- `backend/app/core/learning.py`: learning, briefing, research
- `backend/app/core/document_store.py`: user documents and retrieval
- `frontend/components/chat/ChatPanel.tsx`: Alex chat shell
- `frontend/components/chat/`: plan UI
- `frontend/components/tasks/TaskCard.tsx`: task results and deliverables UI
- `frontend/components/agents/WorkspacePanel.tsx`: skills, knowledge, files

## Local Data You Must Respect

- `backend/data/agents.json`
- `backend/data/teams.json`
- `backend/data/workspaces/<agent_id>/`
- `backend/data/task_deliverables/<task_id>/`
- `backend/data/documents/`

Assume real local state may already exist. Avoid destructive assumptions.

## Code Conventions

- Keep imports at the top of files. No inline imports unless strictly necessary.
- In TypeScript `switch` statements over unions/enums, use exhaustive handling.
- Prefer explicit state machines/models over nullable implicit state.
- Prefer visible user feedback over silent failures or `console.error` only.
- When a backend contract changes, update frontend types and consumers too.

## Validation

Frontend:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

Backend:

```bash
python3 -m pytest backend/tests/test_universal_plan.py
python3 -m pytest backend/tests/test_task_orchestration.py
python3 -m pytest backend/tests/test_smoke.py
```

Run the smallest relevant set, but do not skip validation for risky contract changes.

## Default Mindset

- Favor correctness and observability over cleverness.
- Prefer fixing the contract, not just the symptom.
- Keep the product readable and robust for local iteration.
- If architecture or workflow materially changes, update this file and `docs/llm/PROJECT_BRIEF.md`.
