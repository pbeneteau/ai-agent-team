# AI Agent Team Orchestrator

Local-first multi-agent orchestration for startup work. A top-level associate named **Alex** helps the user create teams, review plans, launch tasks, trigger learning, and inspect results through a chat-first workflow.

This is not a generic chatbot. The product is built around:

- explicit team structures with leads and specialists
- per-agent isolated workspaces
- guarded plan mode before risky execution
- 9-state task lifecycle with PM review gates and agent input requests
- kanban board, sortable list, and Gantt timeline views
- projects, labels, and blocking task relations
- per-task cost tracking with pre-execution estimates and execution wave planning
- task-linked deliverables and progress logs
- structured-output observability
- persistent local state that survives restarts

## Stack

- **Backend**: Python, FastAPI, WebSocket
- **LLM runtime**: Anthropic Claude
- **Task orchestration**: CrewAI
- **Memory and retrieval**: ChromaDB + Markdown skills/files per agent
- **Frontend**: Next.js 14 (App Router), React, Tailwind, shadcn/ui, react-flow, @dnd-kit
- **Local infra**: Redis

## Current Model Defaults

Model tiers are configurable, but the current local defaults force all agents to **Sonnet** unless changed in config.

- `CLAUDE_MODEL_SONNET=claude-sonnet-4-5`
- `CLAUDE_MODEL_OPUS=claude-opus-4-5`
- `FORCE_ALL_AGENTS_MODEL_TIER=sonnet` through app config defaults

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Redis
- An Anthropic API key

### Configuration

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set at least ANTHROPIC_API_KEY
```

### Start Everything

```bash
chmod +x start.sh
./start.sh
```

`start.sh` will:

- create `backend/.env` from the example if missing
- start Redis if it is not already running
- create the backend virtualenv if needed
- install missing backend/frontend dependencies
- run FastAPI on `127.0.0.1:8000`
- run Next.js on `localhost:3000`

### Manual Startup

```bash
# Terminal 1
redis-server

# Terminal 2
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 3
cd frontend
npm install
npm run dev
```

## Local URLs

| Service | URL |
|---|---|
| Frontend | [http://localhost:3000](http://localhost:3000) |
| Backend API | [http://localhost:8000](http://localhost:8000) |
| API Docs | [http://localhost:8000/docs](http://localhost:8000/docs) |

## Product Surface

- `/chat`: main Alex workspace
- `/team`: org chart, agents, workspaces, knowledge panels
- `/tasks`: task management hub with three views:
  - **Board** (default): kanban with drag-and-drop across 6 columns (Triage → Backlog → Queued → In Progress → Review → Done)
  - **List**: sortable table with bulk actions, inline editing, and multi-select
  - **Timeline**: SVG Gantt chart with auto-zoom, status-colored bars, and progress fill
- `/project-context`: project brief, recommendations, global readiness
- `/usage`: token/cost monitoring and structured-output channel monitoring
- `/team-builder`: legacy/alternate team-building surface built on the same chat shell

## Architecture

```text
ai-agent-team/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app + restart recovery
│   │   ├── config.py                 # Pydantic settings and model defaults
│   │   ├── api/routes/
│   │   │   ├── chat.py               # Alex websocket, plan mode, learning triggers
│   │   │   ├── agents.py             # Agent APIs, workspace, knowledge readiness
│   │   │   ├── teams.py              # Teams, recommendations, org chart, project context
│   │   │   ├── tasks.py              # Tasks, status transitions, execution, deliverables
│   │   │   ├── task_chat.py          # WebSocket for chat-based task creation
│   │   │   ├── task_comments.py      # Per-task comment threads
│   │   │   ├── task_relations.py     # Blocking/related/duplicate relations between tasks
│   │   │   ├── projects.py           # Project CRUD
│   │   │   ├── labels.py             # Label CRUD
│   │   │   ├── documents.py          # Document upload and briefing flows
│   │   │   └── usage.py              # Token/cost usage and structured-output stats
│   │   ├── core/
│   │   │   ├── agent_factory.py      # Persistent agents/teams + runtime recovery
│   │   │   ├── learning.py           # Learning, rebriefing, research, project briefing
│   │   │   ├── orchestrator.py       # Task engine: status machine, execution, review loop
│   │   │   ├── project_store.py      # JSON-backed project persistence
│   │   │   ├── label_store.py        # JSON-backed label persistence
│   │   │   ├── task_relation_store.py # JSON-backed task relation persistence
│   │   │   ├── task_comment_store.py # JSON-backed task comment persistence
│   │   │   ├── task_sufficiency.py   # LLM-based task description quality check
│   │   │   ├── cost_estimator.py     # Pre-execution cost estimation heuristics
│   │   │   ├── execution_wave.py     # Topological sort for parallel execution batches
│   │   │   ├── structured_json.py    # Structured output runtime + telemetry
│   │   │   ├── universal_plan.py     # Guarded plan state machine
│   │   │   ├── workspace.py          # Per-agent isolated workspaces
│   │   │   ├── document_store.py     # Upload, parsing, vector indexing
│   │   │   └── usage_tracker.py      # Anthropic and structured-flow accounting
│   │   ├── agents/
│   │   │   ├── associate.py          # Alex chat logic + typed actions
│   │   │   ├── base_agent.py         # CrewAI agent builder
│   │   │   └── specialists/          # Role templates
│   │   ├── config/
│   │   │   └── pricing.py            # Anthropic model pricing (Sonnet/Opus)
│   │   ├── memory/                   # Project context, skills, vector store
│   │   ├── models/
│   │   │   ├── task.py               # Task model with 9-state status, cost fields
│   │   │   ├── project.py            # Project model
│   │   │   ├── label.py              # Label model
│   │   │   ├── task_relation.py      # Task relation model (blocks/related/duplicate)
│   │   │   ├── task_comment.py       # Comment model (message/input_request/review_feedback)
│   │   │   └── task_iteration.py     # Iteration tracking model
│   │   └── tools/                    # Agent tools
│   └── data/                         # Local persistent state
├── docs/
│   ├── TASK_SYSTEM_DESIGN.md         # Full task system design rationale
│   ├── TASK_SYSTEM_IMPLEMENTATION_PLAN.md # 6-phase implementation plan
│   └── llm/                          # LLM strategy and coding-agent docs
└── frontend/
    ├── app/                          # Next.js routes
    ├── lib/
    │   ├── api.ts                    # API client, types, WebSocket helpers
    │   ├── config/
    │   │   ├── status-meta.ts        # Status/priority icons and colors
    │   │   └── realtime.ts           # WebSocket broadcast event registry
    │   └── websocket.ts              # Typed WebSocket message union
    ├── components/chat/              # Alex shell, plan UI, team-builder UI
    ├── components/agents/            # Agent workspace UI
    ├── components/tasks/
    │   ├── BoardView.tsx             # Kanban board with drag-and-drop (@dnd-kit)
    │   ├── BoardTaskCard.tsx         # Board card with priority, labels, cost
    │   ├── ListView.tsx              # Sortable table with bulk actions
    │   ├── TimelineView.tsx          # SVG Gantt chart with auto-zoom
    │   ├── TaskDetailView.tsx        # Task detail with sidebar + activity
    │   ├── TaskActivity.tsx          # Comment thread, input/review UI
    │   ├── TaskCreateDialog.tsx      # Form + chat task creation
    │   ├── FilterBar.tsx             # Project/priority/label/team filters
    │   ├── CostIndicator.tsx         # Estimated/live/final cost display
    │   └── ExecutionWaveSuggestion.tsx # Batch execution planner banner
    └── components/project-context/   # Recommendations and readiness UI
```

## Main Workflows

### 1. Alex Chat and Universal Plan Mode

Alex can:

- answer directly
- ask for structured information with dynamic forms
- propose a **task plan** or **team plan**
- request targeted clarifications before confirmation
- trigger learning for existing agents

Plan mode is no longer just prose. Drafts now include structured validation metadata such as:

- `validation_issues`
- `validation_status`
- `execution_eligibility`

Confirmation is only allowed when the backend explicitly marks the draft as eligible.

### 2. Team Creation and Agent Learning

Teams can be created:

- through Alex and plan mode
- through team recommendations in the project context UI
- from templates or custom team APIs

New agents are created with isolated workspaces and are expected to run an automatic learning phase that writes:

- `core_skills`
- `project_context`
- profile/output files in the agent workspace

Existing agents can also be re-initialized through Alex via the learning trigger flow.

### 3. Knowledge and Context Enrichment

There are several complementary knowledge paths:

- **global project context** shared across the product
- **uploaded documents** indexed for Alex and project-wide context
- **agent-specific downloads and notes** in each workspace
- **knowledge readiness audits** with structured recommendations
- **web research flows** that can write reusable research notes

The project context and recommendations surfaces also expose the real structured generation channel used by backend flows.

### 4. Task Lifecycle

Tasks follow a 9-state lifecycle: **Triage → Backlog → Queued → Planning → Executing → Review → Done** (with **Input Needed** and **Cancelled** side-states). Transitions are validated by a state machine.

**Creation**: Tasks can be created via a structured form or a conversational chat interface (with LLM-powered sufficiency analysis). New tasks start in Triage.

**Execution**: When a queued task is executed, the engine:

- generates an execution plan (specialist nodes + lead compilation)
- estimates cost before running (token heuristics per node type)
- runs nodes in dependency-ordered waves with `asyncio.gather`
- tracks actual token usage and cost per node in real-time
- detects `[INPUT_NEEDED]` markers in agent output and pauses for PM input
- lands in Review status for PM approval (never auto-completes to Done)

**Review loop**: The PM can approve (→ Done) or request changes with feedback. Feedback iterations re-run the lead compilation node with PM context injected.

**Organization**: Tasks can be grouped into projects, tagged with labels, and linked via blocking/related/duplicate relations. Blocking relations are enforced at execution time.

**Execution waves**: When multiple tasks are queued, a topological sort suggests parallel execution batches with estimated cost and duration.

### 5. Observability

The app includes dedicated observability for:

- token and cost usage
- model split
- structured-output success/failure by flow
- structured generation channel by flow
- task progress entries with structured flow/channel metadata

The main UI for this is `/usage`.

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key | Yes |
| `REDIS_URL` | Redis connection string | No |
| `CLAUDE_MODEL_SONNET` | Sonnet model name | No |
| `CLAUDE_MODEL_OPUS` | Opus model name | No |
| `CHROMA_PERSIST_DIR` | ChromaDB storage path | No |
| `SERPER_API_KEY` | Web search for research flows | Optional |
| `GITHUB_TOKEN` | GitHub API access for some tooling | Optional |

## Useful Local State

Be careful with local data. This project often runs with meaningful persisted state already present.

Important locations include:

- `backend/data/agents.json`
- `backend/data/teams.json`
- `backend/data/tasks.json`
- `backend/data/projects.json`
- `backend/data/labels.json`
- `backend/data/task_relations.json`
- `backend/data/task_comments.json`
- `backend/data/workspaces/`
- `backend/data/task_deliverables/`
- `backend/data/documents/`
- `backend/data/knowledge_readiness/`
- `backend/data/usage.json`

## Validation Commands

```bash
# Health
curl http://localhost:8000/health

# Core API lists
curl http://localhost:8000/api/agents/
curl http://localhost:8000/api/teams/
curl http://localhost:8000/api/tasks/
curl http://localhost:8000/api/projects/
curl http://localhost:8000/api/labels/

# Task system
curl http://localhost:8000/api/tasks/execution-wave-suggestion

# Usage and structured-output observability
curl http://localhost:8000/api/usage/

# Recommendations and readiness
curl http://localhost:8000/api/teams/recommendations
curl http://localhost:8000/api/agents/readiness/global
```

### Common Test Commands

```bash
python3 -m pytest backend/tests/test_universal_plan.py
python3 -m pytest backend/tests/test_task_orchestration.py
python3 -m pytest backend/tests/test_structured_json.py
python3 -m pytest backend/tests/test_knowledge_recommendations.py
python3 -m pytest backend/tests/test_smoke.py

cd frontend
npm run test
npm run build
```
