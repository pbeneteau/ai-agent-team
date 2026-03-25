# Task System Redesign — Linear-Inspired, Agent-Native

## 1. Executive Summary

### The problem

The current task system is a **one-shot execution pipeline** — tasks are created, immediately decomposed into agent nodes, executed, and marked done or failed. There is no backlog, no planning phase visible to the PM, no iteration loop, no inter-task dependencies, no board view, and no cost visibility. A PM cannot organize work ahead of time, track progress across multiple tasks, or provide structured feedback to agents.

### The solution

Redesign the task system as a **Linear-inspired project management layer** where the workers happen to be AI agents. The PM gets familiar concepts — backlog, board, priorities, labels, projects, relations — adapted for the unique properties of AI execution: instant availability, token-based cost, minute-scale execution, and parallel processing.

### Key design principles

1. **Familiar PM vocabulary** — Backlog, Board, Queue, Review. A PM who knows Linear navigates without docs.
2. **Agent-native mechanics** — No story points (tokens instead), no standups (real-time streaming), no sprint ceremonies (system-suggested execution waves).
3. **Human-in-the-loop** — Agents can pause and ask the PM for input. PMs review results before marking done. Iteration is a first-class workflow, not a workaround.
4. **Linear-compatible data model** — Every entity maps to a Linear API concept. Bidirectional sync is a future migration, not a rewrite.
5. **Cost transparency** — Token usage and estimated cost visible on every task, project, and execution wave.

---

## 2. Data Model

### 2.1 Entities Overview

```
Project ──1:N──> Task ──1:N──> TaskNode (execution)
   │                │
   │                ├──1:N──> TaskRelation (blocks, related, duplicate)
   │                ├──1:N──> TaskComment (chat/feedback thread)
   │                ├──1:N──> TaskIteration (execution cycles)
   │                ├──N:M──> Label
   │                └──1:N──> TaskDeliverable
   │
   └──N:M──> Label

Label
TaskView (saved filter/sort configurations)
```

### 2.2 Task (core entity)

The central entity. Maps to Linear's `Issue`.

```
Task
├── Identity
│   ├── id: UUID
│   ├── identifier: str              # Human-readable key, e.g. "TASK-42"
│   ├── title: str
│   ├── description: str             # Rich text / Markdown
│   └── created_at, updated_at: datetime
│
├── Workflow
│   ├── status: TaskStatus           # See state machine (section 3)
│   ├── priority: TaskPriority       # urgent | high | medium | low | none
│   ├── sort_order: float            # Manual ordering within a status column
│   └── status_changed_at: datetime  # When status last transitioned
│
├── Organization
│   ├── project_id: Optional[UUID]   # Parent project
│   ├── labels: list[UUID]           # Label references
│   ├── creator_type: CreatorType    # human_form | human_chat | system
│   └── creator_id: Optional[str]    # Who/what created it
│
├── Assignment
│   ├── assigned_team_id: Optional[UUID]
│   ├── assigned_agent_id: Optional[UUID]    # Specific agent (optional)
│   ├── assigned_agent_ids: list[UUID]       # All agents in execution plan
│   └── assignment_strategy: AssignmentStrategy  # specific | team_auto | role_based
│
├── Execution
│   ├── execution_mode: TaskExecutionMode    # auto | standalone | dependency_graph
│   ├── execution_plan: TaskExecutionPlan    # DAG of nodes (unchanged concept)
│   ├── execution_eligibility: TaskExecutionEligibility
│   ├── execution_blockers: list[str]
│   └── current_iteration: int              # 0 = not yet executed, 1+ = iteration count
│
├── Results
│   ├── result: Optional[str]               # Final output (Markdown)
│   ├── sources: list[str]
│   ├── assumptions: list[str]
│   ├── warnings: list[str]
│   ├── deliverables: list[TaskDeliverable]
│   └── deliverables_dir: Optional[str]
│
├── Cost tracking
│   ├── estimated_input_tokens: Optional[int]
│   ├── estimated_output_tokens: Optional[int]
│   ├── estimated_cost_usd: Optional[float]
│   ├── actual_input_tokens: int             # Accumulated across iterations
│   ├── actual_output_tokens: int
│   └── actual_cost_usd: float
│
├── Error state
│   ├── error: Optional[str]
│   ├── error_type: Optional[str]
│   ├── error_traceback: Optional[str]
│   └── failure_stage: Optional[str]
│
├── Context
│   ├── context_document_ids: list[UUID]
│   ├── brief_revision: Optional[int]
│   └── brief_fingerprint: Optional[str]
│
└── Metadata
    ├── progress_log: list[TaskProgressEntry]  # Execution events timeline
    ├── archived_at: Optional[datetime]
    └── cancelled_at: Optional[datetime]
```

### 2.3 Project

Groups related tasks. Maps to Linear's `Project`.

```
Project
├── id: UUID
├── identifier: str                # e.g. "PRJ-3"
├── name: str
├── description: Optional[str]
├── status: ProjectStatus          # planned | active | paused | completed | cancelled
├── color: str                     # Hex color for UI
├── icon: Optional[str]            # Emoji or icon key
├── lead_agent_id: Optional[UUID]  # Default team lead for tasks in this project
├── default_team_id: Optional[UUID]
├── labels: list[UUID]
├── target_date: Optional[date]    # Soft deadline for PM planning
├── sort_order: float
├── created_at, updated_at: datetime
├── total_estimated_cost_usd: float  # Sum of task estimates
└── total_actual_cost_usd: float     # Sum of actual costs
```

### 2.4 Label

Free-form tags. Maps to Linear's `IssueLabel`.

```
Label
├── id: UUID
├── name: str                 # e.g. "frontend", "urgent-fix", "research"
├── color: str                # Hex color
├── group: Optional[str]      # Group name for organized label sets
├── description: Optional[str]
└── created_at: datetime
```

### 2.5 TaskRelation

Directed relationships between tasks. Maps to Linear's `IssueRelation`.

```
TaskRelation
├── id: UUID
├── type: RelationType         # blocks | related | duplicate
├── source_task_id: UUID       # The task that "blocks" / "is related to" / "duplicates"
├── target_task_id: UUID       # The task that "is blocked by" / ...
└── created_at: datetime
```

Semantics:
- `blocks`: source must complete before target can execute. System enforces this.
- `related`: informational link. No execution impact.
- `duplicate`: source is a duplicate of target. System suggests merging or cancelling.

### 2.6 TaskComment

Chat-like thread on a task for PM-agent interaction. Maps to Linear's `Comment`.

```
TaskComment
├── id: UUID
├── task_id: UUID
├── author_type: CommentAuthorType   # human | agent | system
├── author_id: Optional[str]         # Agent ID or user identifier
├── author_name: str
├── body: str                        # Markdown content
├── comment_type: CommentType        # message | input_request | review_feedback | status_change
├── iteration: int                   # Which iteration this comment belongs to
├── resolved: bool                   # For input_requests — has PM responded?
└── created_at: datetime
```

### 2.7 TaskIteration

Tracks each execution cycle of a task. New concept — no Linear equivalent (Linear uses activity log).

```
TaskIteration
├── id: UUID
├── task_id: UUID
├── iteration_number: int            # 1, 2, 3...
├── trigger: IterationTrigger        # initial | review_feedback | input_provided | manual_rerun
├── feedback: Optional[str]          # PM feedback that triggered this iteration
├── execution_plan_snapshot: dict    # Plan state at start of this iteration
├── started_at: datetime
├── completed_at: Optional[datetime]
├── input_tokens: int
├── output_tokens: int
├── cost_usd: float
└── result_summary: Optional[str]    # Brief summary of what changed
```

### 2.8 TaskView (saved views)

Persisted filter/sort/group configurations. Maps to Linear's `CustomView`.

```
TaskView
├── id: UUID
├── name: str                     # e.g. "My active tasks", "Frontend work"
├── view_type: ViewType           # board | list | timeline
├── filters: dict                 # {status: [...], priority: [...], labels: [...], project_id: ...}
├── sort_by: Optional[str]        # "priority" | "created_at" | "cost" | "status" | "sort_order"
├── sort_direction: str           # "asc" | "desc"
├── group_by: Optional[str]       # "status" | "priority" | "project" | "label" | "assignee"
├── is_default: bool
└── created_at: datetime
```

---

## 3. Status Machine

### 3.1 Task statuses

```
                          ┌─────────────────────────────────────────────────┐
                          │                                                 │
   ┌─────────┐      ┌────▼────┐      ┌────────┐      ┌──────────┐         │
   │ TRIAGE  │─────>│ BACKLOG │─────>│ QUEUED │─────>│ PLANNING │         │
   └────┬────┘      └────┬────┘      └───┬────┘      └──┬───┬───┘         │
        │                │               │               │   │             │
        │                │               │               │   └──────┐      │
        │                │               │               ▼          ▼      │
        │                │               │         ┌───────────┐ ┌──────────────┐
        │                │               └────────>│ EXECUTING │ │ INPUT_NEEDED │
        │                │                         └──┬────┬───┘ └──────┬───────┘
        │                │                            │    │            │
        │                │                            │    └────────────┘
        │                │                            ▼          │
        │                │                      ┌─────────┐     │
        │                │                      │ REVIEW  │<────┘
        │                │                      └──┬──┬───┘
        │                │                         │  │
        │                │                         │  │ (feedback → re-execute)
        │                │                         │  └──────────────────────┐
        │                │                         ▼                         │
        │                │                      ┌──────┐                    │
        │                │                      │ DONE │              ┌─────▼─────┐
        │                │                      └──────┘              │ EXECUTING │
        │                │                                            └───────────┘
        │                │
        ▼                ▼
   ┌───────────┐
   │ CANCELLED │
   └───────────┘
```

### 3.2 Status definitions

| Status | Linear mapping | Category | Description |
|--------|---------------|----------|-------------|
| `triage` | Triage | triage | Newly created, needs PM attention to categorize and prioritize |
| `backlog` | Backlog | backlog | Triaged and prioritized, not yet scheduled for execution |
| `queued` | Todo | unstarted | Scheduled for execution, waiting its turn |
| `planning` | In Progress | started | System building execution plan (agent decomposition, dependency graph) |
| `executing` | In Progress | started | Agents actively working on the task |
| `input_needed` | In Progress | started | Execution paused — agent needs PM input to continue |
| `review` | In Progress | started | Execution complete — PM reviews result before approving |
| `done` | Done | completed | PM approved the result |
| `cancelled` | Cancelled | cancelled | Abandoned by PM |

### 3.3 Transition rules

| From | To | Trigger | Auto/Manual |
|------|----|---------|-------------|
| `triage` | `backlog` | PM triages (sets priority, labels, project) | Manual |
| `triage` | `queued` | PM triages and queues directly | Manual |
| `triage` | `cancelled` | PM discards | Manual |
| `backlog` | `queued` | PM schedules for execution | Manual |
| `backlog` | `cancelled` | PM discards | Manual |
| `queued` | `planning` | System picks up task (or PM clicks "Execute") | Auto/Manual |
| `queued` | `cancelled` | PM cancels before execution | Manual |
| `planning` | `executing` | Plan ready, execution starts | Auto |
| `planning` | `input_needed` | Planner needs clarification from PM | Auto |
| `planning` | `cancelled` | PM cancels | Manual |
| `executing` | `review` | All nodes terminal, at least one succeeded | Auto |
| `executing` | `input_needed` | Agent needs PM input mid-execution | Auto |
| `executing` | `cancelled` | PM cancels mid-execution (graceful stop) | Manual |
| `input_needed` | `planning` | PM provides input, resume planning | Auto (on PM response) |
| `input_needed` | `executing` | PM provides input, resume execution | Auto (on PM response) |
| `input_needed` | `cancelled` | PM cancels instead of providing input | Manual |
| `review` | `done` | PM approves result | Manual |
| `review` | `executing` | PM provides feedback → new iteration | Manual (triggers auto) |
| `review` | `cancelled` | PM rejects entirely | Manual |
| `cancelled` | `backlog` | PM un-cancels (restore) | Manual |

### 3.4 Linear sync mapping

For bidirectional Linear sync, the mapping is:

```python
TASK_STATUS_TO_LINEAR_STATE_TYPE = {
    "triage":       "triage",
    "backlog":      "backlog",
    "queued":       "unstarted",
    "planning":     "started",
    "executing":    "started",
    "input_needed": "started",
    "review":       "started",
    "done":         "completed",
    "cancelled":    "cancelled",
}
```

Linear allows multiple custom states per category, so `planning`, `executing`, `input_needed`, and `review` each become a distinct Linear workflow state within the "started" category.

---

## 4. Workflows and Automations

### 4.1 Task creation flow

Two entry points, both ending at the same confirmation step:

**Path A — Form-based creation:**
```
1. PM fills: title, description, priority (optional), team (optional), documents (optional)
2. System runs sufficiency analysis (LLM check):
   - Is the description clear enough for agents to execute?
   - Are there ambiguities that need resolving?
   - Is team/agent assignment resolvable?
3. If insufficient: system asks targeted follow-up questions inline
4. PM confirms → Task created in status: triage (or backlog if PM already triaged)
```

**Path B — Chat-based creation:**
```
1. PM describes intent conversationally ("I need a competitive analysis of...")
2. LLM asks clarifying questions, refines scope, suggests structure
3. LLM generates structured task fields (title, description, priority suggestion, team suggestion)
4. PM reviews and edits the generated fields
5. PM confirms → Task created in status: triage (or backlog)
```

Both paths produce the same `Task` object. The `creator_type` field records which path was used.

### 4.2 Automatic behaviors

| Trigger | Action | Condition |
|---------|--------|-----------|
| Task enters `queued` | Check blocking relations | If blocked by incomplete tasks, add to `execution_blockers` |
| Task enters `queued` | Auto-assign team | If no team assigned and `assignment_strategy = team_auto` |
| Blocking task reaches `done` | Unblock dependent tasks | Re-evaluate `execution_blockers`, clear if resolved |
| All blockers cleared on `queued` task | Start planning | Move to `planning` automatically |
| Plan generation complete | Start execution | Move `planning` → `executing` |
| All nodes terminal | Move to review | If at least one node completed |
| All nodes failed | Move to review | With failure summary (PM still reviews) |
| PM responds to input_needed | Resume execution | Move `input_needed` → `executing` or `planning` |
| PM provides review feedback | New iteration | Increment `current_iteration`, create `TaskIteration`, move → `executing` |
| Task `done` or `cancelled` | Release agents | Clear occupancy for all assigned agents |
| Task created from chat | Auto-triage | If PM set priority during chat, skip `triage` → `backlog` |

### 4.3 Execution waves (replaces cycles/sprints)

No fixed-duration sprints. Instead, the system suggests **execution waves**:

```
System analyzes queued tasks:
  1. Build dependency graph across all queued tasks
  2. Identify which tasks can run in parallel (no blocking relations)
  3. Check agent availability (which teams are idle)
  4. Estimate cost for the batch

System proposes to PM:
  "5 tasks are ready to execute. Estimated cost: ~$3.20, ~12 minutes.
   [Task A, Task B, Task C] can run in parallel.
   [Task D] will start after Task A completes (blocked).
   [Task E] will start after Task B completes (blocked).

   [Execute all] [Select tasks] [Not now]"
```

This is surfaced as a **smart suggestion** in the UI, not a formal entity. No cycle model to maintain — just an intelligent batch proposal.

### 4.4 The input_needed flow

When an agent encounters a question it cannot resolve:

```
1. Agent outputs a structured input_request:
   { "type": "input_needed", "question": "...", "context": "...", "options": [...] }

2. System:
   - Pauses the node (status remains RUNNING but flagged as waiting)
   - Creates a TaskComment with comment_type = "input_request"
   - Moves task to input_needed status
   - Broadcasts WebSocket event: task_input_needed
   - Sends notification to PM

3. PM sees:
   - Task card shows "Input needed" badge with agent avatar
   - Opening the task shows the chat thread with the agent's question
   - PM types a response (or selects from suggested options)

4. On PM response:
   - System creates a TaskComment with comment_type = "message"
   - Marks the input_request as resolved
   - Injects PM's response into the agent's context
   - Resumes node execution
   - Task moves back to executing
```

### 4.5 The review + iteration flow

```
1. Execution completes → task moves to review

2. PM sees:
   - Result summary with deliverables
   - Quality indicators (sources, assumptions, warnings, scores)
   - Comment thread showing execution history

3. PM can:
   a) Approve → task moves to done
   b) Request changes → PM writes feedback in comment thread
      - System creates new TaskIteration
      - Injects PM feedback as additional context
      - Relevant nodes re-execute with feedback
      - Task moves back to executing
      - On completion, returns to review (iteration_number incremented)
   c) Cancel → task moves to cancelled
```

---

## 5. Linear API Compatibility Mapping

### 5.1 Entity mapping

| Our entity | Linear entity | Sync direction | Notes |
|-----------|---------------|----------------|-------|
| Task | Issue | Bidirectional | Core sync unit |
| Project | Project | Bidirectional | 1:1 mapping |
| Label | IssueLabel | Bidirectional | 1:1 mapping |
| TaskRelation | IssueRelation | Bidirectional | Same relation types |
| TaskComment | Comment | Our → Linear | Agent comments sync as Linear comments |
| TaskIteration | — | Our → Linear (as comment) | No Linear equivalent; sync as activity |
| TaskView | CustomView | Our → Linear | Can mirror saved views |
| TaskNode | — | — | Internal execution detail, not synced |
| TaskDeliverable | Attachment | Our → Linear | Files sync as attachments |

### 5.2 Field mapping

| Our field | Linear field | Notes |
|-----------|-------------|-------|
| `task.identifier` | `issue.identifier` | Format must match team prefix (e.g., "TASK-42") |
| `task.title` | `issue.title` | Direct |
| `task.description` | `issue.description` | Markdown compatible |
| `task.status` | `issue.state` | Via workflow state mapping (section 3.4) |
| `task.priority` | `issue.priority` | Same 5-level scale (0-4 in Linear, 0=none) |
| `task.project_id` | `issue.project` | Direct reference |
| `task.labels` | `issue.labels` | N:M relationship, same concept |
| `task.assigned_agent_id` | `issue.assignee` | Agent maps to a Linear "bot user" or team member |
| `task.sort_order` | `issue.sortOrder` | Float for manual positioning |
| `task.created_at` | `issue.createdAt` | Direct |
| `task.estimated_cost_usd` | `issue.estimate` | Custom field — Linear estimate is points-based |
| `task.actual_cost_usd` | — | Custom field on Linear side |

### 5.3 Priority mapping

| Our priority | Our value | Linear priority | Linear value |
|-------------|-----------|----------------|--------------|
| `none` | 0 | No priority | 0 |
| `low` | 1 | Low | 4 |
| `medium` | 2 | Medium | 3 |
| `high` | 3 | High | 2 |
| `urgent` | 4 | Urgent | 1 |

Note: Linear uses inverted numbering (1 = highest). The sync layer handles this inversion.

---

## 6. Frontend Views

### 6.1 Board View (Kanban)

The primary view for day-to-day task management.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [+ New task]  [Filter ▾]  [Group by: Status ▾]   🔍 Search    Board│List│Timeline │
├──────────┬───────────┬───────────┬─────────────────┬──────────┬─────────────┤
│ TRIAGE   │ BACKLOG   │ QUEUED    │ IN PROGRESS     │ REVIEW   │ DONE        │
│ (3)      │ (12)      │ (4)       │ (2)             │ (1)      │ (8)         │
├──────────┼───────────┼───────────┼─────────────────┼──────────┼─────────────┤
│┌────────┐│┌─────────┐│┌─────────┐│┌───────────────┐│┌────────┐│┌───────────┐│
││ TASK-58││ │ TASK-31 │││ TASK-45 │││ ▶ TASK-39     │││TASK-38 │││ ✓ TASK-22 ││
││        ││ │         │││         │││ Executing      │││        │││           ││
││ Comp.  ││ │ Market  │││ Code    │││ ████░░ 4/6     │││ Pitch  │││ Market    ││
││ analys.││ │ research│││ review  │││               │││ deck   │││ sizing    ││
││        ││ │         │││         │││ 🤖 DevTeam    │││        │││           ││
││ 🟡 Med ││ │ 🔴 High │││ 🟡 Med  │││ ~$1.20        │││🔴 High │││ ✓ $0.85  ││
││ research││ │ Q2-plan │││ tech    │││ research tech │││ Q2     │││ Q2-plan   ││
│└────────┘│ └─────────┘│└─────────┘│└───────────────┘│└────────┘│└───────────┘│
│┌────────┐│┌─────────┐│┌─────────┐│┌───────────────┐│          │┌───────────┐│
││ TASK-57││ │ TASK-29 │││ TASK-44 │││ ⏸ TASK-41     ││          ││ ✓ TASK-19 ││
││        ││ │         │││         │││ Input needed   ││          ││           ││
││ New    ││ │ User    │││ API     │││ "Which cloud   ││          ││ Legal     ││
││ feature││ │ persona │││ integr. │││  provider?"    ││          ││ review    ││
││ idea   ││ │ study   │││         │││               ││          ││           ││
││ —— None││ │ 🟡 Med  │││ 🔴 High │││ 🟡 Med        ││          ││ ✓ $0.42  ││
│└────────┘│ └─────────┘│└─────────┘│└───────────────┘│          │└───────────┘│
│          │            │           │                 │          │             │
│ + Add    │ + Add      │           │                 │          │             │
└──────────┴───────────┴───────────┴─────────────────┴──────────┴─────────────┘
```

**Card anatomy:**
- Identifier + title
- Status sub-state badge (for "In Progress": planning / executing with progress / input_needed)
- Assigned team/agent avatar
- Priority indicator (color dot)
- Labels (colored chips)
- Cost indicator (estimated or actual)
- Progress bar (nodes completed / total) when executing

**Interactions:**
- Drag-drop cards between columns (triggers status transition with validation)
- Click card → opens detail side panel or full page
- `+ Add` at column bottom → quick task creation in that status
- Group by: Status (default) | Priority | Project | Label | Assignee
- Filter by: any field combination
- Column for "In Progress" merges `planning`, `executing`, `input_needed` with sub-badges

### 6.2 List View (Table)

Power-user view for bulk operations and sorting.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  [+ New task]  [Filter ▾]  [Group by: None ▾]   🔍 Search    Board│List│Timeline │
├────┬──────┬────┬─────────────────────────┬──────────┬─────────┬──────┬──────┤
│ ☐  │ ID   │ !! │ Title                   │ Status   │ Assign. │ Cost │ Upd. │
├────┼──────┼────┼─────────────────────────┼──────────┼─────────┼──────┼──────┤
│ ☐  │ T-45 │ 🟡 │ Code architecture review│ Queued   │ DevTeam │ ~$2  │ 2m   │
│ ☐  │ T-44 │ 🔴 │ API integration plan    │ Queued   │ DevTeam │ ~$3  │ 5m   │
│ ☐  │ T-41 │ 🟡 │ Cloud migration strategy│ ⏸ Input  │ DevOps  │ $1.1 │ 12m  │
│ ☐  │ T-39 │ 🟡 │ Competitive landscape   │ ▶ Exec.  │ ResTeam │ $1.2 │ 1m   │
│ ☐  │ T-38 │ 🔴 │ Pitch deck analysis     │ Review   │ BizTeam │ $0.9 │ 30m  │
│ ☐  │ T-31 │ 🔴 │ Market research deep    │ Backlog  │ ResTeam │ ~$4  │ 1h   │
├────┴──────┴────┴─────────────────────────┴──────────┴─────────┴──────┴──────┤
│ ☑ 2 selected   [Set priority ▾]  [Add label ▾]  [Move to ▾]  [Cancel]      │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columns** (configurable):
- Checkbox (multi-select)
- Identifier
- Priority (icon)
- Title
- Status (with sub-state)
- Assignee (team or agent)
- Labels
- Project
- Estimated / actual cost
- Updated at
- Created at

**Interactions:**
- Click column header → sort
- Checkbox → bulk actions bar appears (set priority, add label, move status, cancel)
- Inline editing: click priority/status/assignee to change
- Row click → open detail
- Group by any column

### 6.3 Timeline View (Gantt)

Dependency visualization across tasks.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  [Filter ▾]  [Zoom: Day ▾]                           Board│List│Timeline   │
├─────────────────────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬────────────┤
│                     │10:00│10:15│10:30│10:45│11:00│11:15│11:30│            │
├─────────────────────┼─────┴─────┴─────┴─────┴─────┴─────┴─────┴────────────┤
│ T-39 Competitive    │ ██████████████████████░░░░░░░░░░                      │
│   landscape         │ ├─Node1─┤├─Node2─┤├──Node3───┤                       │
│                     │                                                       │
│ T-44 API integr.    │           ████████████████████████                    │
│   (blocked by T-39) │     ------>├─Node1─┤├──Node2──┤                      │
│                     │                                                       │
│ T-45 Code review    │ ████████████████████                                  │
│                     │ ├──Node1──┤├Node2┤                                    │
│                     │                                                       │
│ T-41 Cloud migr.    │ ███████░░░⏸ Input needed                              │
│                     │ ├Node1┤ ⏸                                             │
└─────────────────────┴───────────────────────────────────────────────────────┘

Legend: ██ completed  ░░ in progress  ── not started  ⏸ paused  ----> dependency
```

**Features:**
- Horizontal bars show task duration (actual for past, estimated for future)
- Arrows between bars show `blocks` relations
- Expandable: click a task bar to reveal internal nodes
- Zoom levels: minutes (during execution), hours, days
- Color-coded by status
- Drag bar endpoints to adjust (no-op for AI tasks, but useful for `target_date` on projects)

**Integration with existing React Flow:**
- The internal node dependency graph (currently in `ExecutionTimeline.tsx`) remains for the expanded per-task view
- The timeline view is a new component showing *inter-task* dependencies
- Both can coexist: timeline for the PM, node graph for debugging execution

### 6.4 Task Detail View (redesigned)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Back to tasks                                            TASK-39          │
├──────────────────────────────────┬───────────────────────────────────────────┤
│                                  │ Properties                               │
│ Competitive Landscape Analysis   │ ┌───────────────────────────────────────┐ │
│                                  │ │ Status:    [▶ Executing      ▾]      │ │
│ Description...                   │ │ Priority:  [🟡 Medium        ▾]      │ │
│                                  │ │ Assignee:  [🤖 Research Team ▾]      │ │
│ ─────────────────────────────    │ │ Project:   [Q2 Planning     ▾]      │ │
│                                  │ │ Labels:    [research] [market] [+]   │ │
│ [Readout] [Execution] [Files]    │ │ Iteration: 1                         │ │
│ [Sources] [Activity]             │ │ Cost:      $1.20 (est. ~$2.00)       │ │
│                                  │ │ Created:   2 hours ago               │ │
│ ┌──────────────────────────────┐ │ │ Updated:   1 minute ago              │ │
│ │ Result / execution content   │ │ └───────────────────────────────────────┘ │
│ │ displayed here based on      │ │                                           │
│ │ selected tab                 │ │ Relations                                 │
│ │                              │ │ ┌───────────────────────────────────────┐ │
│ │                              │ │ │ Blocks: TASK-44 API integration      │ │
│ │                              │ │ │ Related: TASK-31 Market research     │ │
│ │                              │ │ │ [+ Add relation]                     │ │
│ │                              │ │ └───────────────────────────────────────┘ │
│ └──────────────────────────────┘ │                                           │
│                                  │                                           │
│ ─────────────────────────────    │                                           │
│ Activity & Chat                  │                                           │
│ ┌──────────────────────────────┐ │                                           │
│ │ 🤖 Agent: Execution started  │ │                                           │
│ │ 🤖 Agent: Node 1 complete    │ │                                           │
│ │ 👤 PM: Can you also include  │ │                                           │
│ │    pricing data?             │ │                                           │
│ │ 🤖 Agent: Noted, including...│ │                                           │
│ │                              │ │                                           │
│ │ [Type a message...]   [Send] │ │                                           │
│ └──────────────────────────────┘ │                                           │
└──────────────────────────────────┴───────────────────────────────────────────┘
```

**Key changes from current:**
- Right sidebar: editable properties (status, priority, labels, project, relations)
- Activity/chat thread at bottom: unified view of execution events + PM comments
- Chat input always available: PM can comment at any time (during execution → becomes context for agents)
- Iteration history accessible via tabs

---

## 7. Migration from Current System

### 7.1 Strategy: incremental, non-breaking

The migration is additive. No existing functionality breaks — new features layer on top.

### 7.2 Migration phases

**Phase 0 — Data model extension (no UI changes)**
- Add new fields to `TaskResponse`: `identifier`, `labels`, `project_id`, `sort_order`, `current_iteration`, cost fields, `status_changed_at`, `archived_at`, `cancelled_at`
- Add new enums: expanded `TaskStatus` (9 states), `TaskPriority` (5 levels)
- Add new models: `Project`, `Label`, `TaskRelation`, `TaskComment`, `TaskIteration`, `TaskView`
- Existing tasks migrate: `pending` → `backlog`, `running` → `executing`, `completed` → `done`, `failed` → `review` (with error), `partial` → `review` (with partial result)
- Add `identifier` sequence counter to settings
- Persist new entities in separate JSON files (projects.json, labels.json, etc.) until PostgreSQL migration

**Phase 1 — New status machine + basic board**
- Implement full status transition logic in orchestrator
- Build board view (kanban) as new default tasks page
- Add status transition API endpoints
- Keep existing grid view accessible as fallback
- Wire up drag-drop status changes

**Phase 2 — Projects, labels, relations**
- CRUD API for projects, labels
- Task relation API (blocks/related/duplicate)
- Auto-blocking enforcement in execution queue
- Filter/group UI controls in board and list views

**Phase 3 — Task creation redesign**
- Form-based creation with sufficiency analysis
- Chat-based creation flow
- Remove or repurpose the main chat
- Triage inbox view

**Phase 4 — Comments, input_needed, review flow**
- TaskComment API and real-time sync
- `input_needed` workflow (agent pause → PM response → resume)
- Review flow with iteration support
- Activity feed on task detail

**Phase 5 — List view + timeline view**
- Sortable/filterable table view
- Bulk actions
- Timeline/Gantt view with inter-task dependencies
- Saved views (TaskView persistence)

**Phase 6 — Cost tracking + execution waves**
- Pre-execution cost estimation
- Cost display on tasks, projects
- Smart execution wave suggestions
- Cost aggregation on projects

### 7.3 Status migration mapping

| Current status | New status | Rationale |
|---------------|-----------|-----------|
| `pending` | `backlog` | Pending tasks become backlog items |
| `running` | `executing` | Direct mapping |
| `completed` | `done` | Skip review for existing completed tasks |
| `failed` | `review` | Failed tasks go to review so PM can decide: retry or cancel |
| `partial` | `review` | Partial results need PM decision |

---

## 8. Implementation Plan

### Phase 0 — Data model extension
**Effort:** ~2 days
**Files:** `models/task.py`, `models/project.py` (new), `models/label.py` (new), `models/relations.py` (new), `orchestrator.py`, `frontend/lib/api.ts`, `frontend/lib/config/status-meta.ts`
**Risk:** Low — additive changes, no breaking modifications

### Phase 1 — Status machine + board view
**Effort:** ~4 days
**Files:** `orchestrator.py` (status transitions), `api/routes/tasks.py` (new endpoints), `frontend/app/tasks/page.tsx` (board view), `frontend/components/tasks/BoardView.tsx` (new), `frontend/components/tasks/TaskCard.tsx` (redesigned)
**Risk:** Medium — status machine is the core behavioral change
**Dependencies:** Phase 0

### Phase 2 — Projects, labels, relations
**Effort:** ~3 days
**Files:** `api/routes/projects.py` (new), `api/routes/labels.py` (new), `core/project_store.py` (new), `orchestrator.py` (blocking enforcement), `frontend/components/tasks/FilterBar.tsx` (new)
**Risk:** Low — mostly CRUD + UI
**Dependencies:** Phase 0

### Phase 3 — Task creation redesign
**Effort:** ~4 days
**Files:** `api/routes/tasks.py` (creation flow), `core/task_creation.py` (new — sufficiency analysis), `frontend/components/tasks/TaskCreateFlow.tsx` (new), chat components
**Risk:** Medium — replaces existing creation UX
**Dependencies:** Phase 1

### Phase 4 — Comments, input_needed, review
**Effort:** ~4 days
**Files:** `core/orchestrator.py` (input_needed/review transitions), `api/routes/comments.py` (new), `frontend/components/tasks/TaskActivity.tsx` (new), `frontend/components/tasks/TaskDetailView.tsx` (redesigned)
**Risk:** High — changes agent execution flow, adds human-in-the-loop
**Dependencies:** Phase 1, Phase 3

### Phase 5 — List view + timeline
**Effort:** ~4 days
**Files:** `frontend/components/tasks/ListView.tsx` (new), `frontend/components/tasks/TimelineView.tsx` (new), `api/routes/views.py` (new)
**Risk:** Low — primarily frontend work
**Dependencies:** Phase 2

### Phase 6 — Cost tracking + execution waves
**Effort:** ~3 days
**Files:** `core/orchestrator.py` (cost estimation, wave suggestions), `core/usage_tracker.py` (per-task tracking), `frontend/components/tasks/CostIndicator.tsx` (new), `frontend/components/tasks/ExecutionWaveSuggestion.tsx` (new)
**Risk:** Low — builds on existing usage tracker
**Dependencies:** Phase 1

**Total estimated effort: ~24 days**
**Recommended order: 0 → 1 → 2 → 3 → 4 → 5 → 6** (critical path through Phases 0-1-3-4)

---

## 9. Open Decisions

| # | Decision | Options | Recommendation | Impact |
|---|----------|---------|----------------|--------|
| 1 | **Task identifier format** | `TASK-42` vs `{PROJECT}-42` (like Linear's team prefix) | `{PROJECT}-42` — familiar to Linear users, auto-scoped | Phase 0 |
| 2 | **Where does the PM chat live?** | Per-task chat only vs global chat + per-task | Per-task only — kills the unfocused general chat, all conversation is contextual | Phase 3 |
| 3 | **Review auto-approval** | Always require review vs configurable per-project | Configurable — some projects are low-stakes, auto-approve saves PM time | Phase 4 |
| 4 | **Execution wave UI** | Toast notification vs dedicated panel vs dashboard widget | Dashboard widget on tasks page — persistent, not dismissible | Phase 6 |
| 5 | **PostgreSQL migration timing** | Before or after task redesign | After Phase 2 — the JSON persistence works for now, and redesigning both simultaneously is risky. PostgreSQL migration becomes Phase 2.5 with clean schema from the new model. | Phase 2.5 |
| 6 | **Linear sync implementation** | Webhook-based vs polling vs hybrid | Webhook for Linear→us, API push for us→Linear. Design the sync adapter as a separate service/module. | Post-Phase 6 |
| 7 | **Node editability** | PM can edit auto-generated nodes before execution vs read-only | Read-only in v1, editable in v2 — auto-generation is the value prop, editing adds complexity | Phase 1 |
| 8 | **Multi-project task** | Task belongs to one project vs many | One project — matches Linear, simpler. Use labels for cross-cutting concerns. | Phase 0 |
