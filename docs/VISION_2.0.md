# Product Strategy & Architecture Vision 2.0
**The Artifact-First Orchestrator: From Babysitting AI to Managing Outcomes**

## 1. Executive Summary
**The Problem:** Our V1 architecture suffered from the "AI UX Crisis." We tried to build both a conversational chatbot (Alex) and a manual, 9-state Kanban board. This forced the user to context-switch between chatting with an AI and micromanaging its execution nodes. We built a system that generated *more* work for the Product Manager, not less.

**The Pivot:** We are abandoning the "Jira for Bots" and "Chatbot" paradigms. We are shifting entirely to the **Pull Request (Artifact-First) Model**. 
Humans do not want to manage the *process* of AI; they want to review the *outcomes*. Our product is no longer a chat interface or a task board. It is an **Autonomous Agency**. The user provides a strictly validated brief, the AI workforce executes in parallel, and the system delivers a version-controlled artifact for human review and contextual iteration.

---

## 2. The Core Product Loop (The "Brief-to-PR" Pipeline)

The entire user experience is now reduced to four highly polished, frictionless steps:

### Phase 1: The Smart Brief (Input)
*   **The UX:** The user clicks "New Deliverable." They are presented with a clean, structured form (Title, Goal, Context, Description). 
*   **The Magic:** As the user types, the frontend debounces the input and hits our `sufficiency-check` API. Vague sentences are instantly highlighted in yellow. 
*   **Example:** User types *"Write a competitive analysis."* The system highlights it and prompts: *"⚠️ Missing constraints: Which competitors? US or EU market? What dimensions (Pricing, UX)?"*
*   **The Value:** We force the human to write a perfect prompt *before* we spend a single Anthropic token on execution.

### Phase 2: The Black Box (Execution)
*   **The UX:** The user clicks "Delegate to Team" and walks away. There is no Kanban board to watch.
*   **The Magic:** The backend takes the perfect spec, builds the Directed Acyclic Graph (DAG), spins up a Lead Agent and Specialists, and executes the work in parallel. 
*   **Auto-Resolution:** If an agent gets stuck, it does *not* pause and wait for the user. It makes a safe assumption, logs it, and keeps moving.

### Phase 3: The Pull Request (Review)
*   **The UX:** The user receives a notification: *"Deliverable Ready."* They open a clean Document/Code Editor UI. 
*   **The Magic:** They are not reviewing a task ticket; they are reviewing the actual Artifact (`v1`). A sidebar displays the sources the agents used and the assumptions they made during the "Black Box" phase.

### Phase 4: Contextual Iteration (Diffs)
*   **The UX:** The user highlights a specific paragraph or block of code and adds a comment: *"Make this section more aggressive and focus on enterprise pricing."*
*   **The Magic:** The backend triggers a targeted iteration. The agent rewrites *only* that section. The UI updates to `v2`, displaying a standard red/green visual diff so the user can instantly see what changed.

---

## 3. Unifying Code and Content
This architecture treats **all work as Files/Artifacts**. Whether the user is asking for a Next.js API route or a Q3 Marketing Strategy, the backend handles it identically:
1.  **Unified Storage:** Both code and text are generated as files in the agent's isolated workspace.
2.  **Unified Diffs:** We use standard text-differencing algorithms for both code and markdown.
3.  **Unified Delivery:** Once the user approves the Artifact, they can either download the Markdown or click "Push to GitHub" to deploy the code via our Git Provider integrations.

---

## 4. Deprecation Notice: What We Are Killing
To achieve this clean vision, we must ruthlessly delete legacy features that add cognitive load and backend fragility.

*   **KILL: Global Chat (`/chat/ws`).** No more conversational task creation. Chat is a lazy UX for complex specs. We use Smart Forms exclusively.
*   **KILL: The 9-State Kanban Board.** Delete `triage`, `backlog`, `queued`, `planning`, `input_needed`, and `partial`. Tasks now have 3 states: `Drafting` (AI working), `In Review` (Human reading), `Approved` (Done).
*   **KILL: `input_needed` Deadlocks.** Agents no longer pause execution indefinitely. They state their assumptions and finish the draft.
*   **KILL: Granular Agent IT Admin.** Delete `AgentGitBindingResolved` per agent. Git and MCP tools are now bound at the *Team* or *Project* level.
*   **KILL: The Organigramme API.** Visualizing fake AI corporate hierarchies is vanity UI. 

---

## 5. Backend Architecture Redesign (Enterprise-Grade)
To support the Artifact-First model at scale, the backend must undergo the following structural shifts:

### A. State Management: Postgres + pgvector
*   **Action:** Delete all `data/*.json` file persistence. 
*   **Why:** JSON files will corrupt under concurrent execution waves. We are migrating to a managed PostgreSQL database for ACID-compliant relational data (Projects, Artifacts, Teams) and using the `pgvector` extension to replace local ChromaDB for agent memory/RAG.

### B. Durable Execution: Temporal.io (or Celery/Redis)
*   **Action:** Rip out `asyncio.gather` for long-running LLM orchestration.
*   **Why:** If the FastAPI server restarts, `asyncio` drops all running tasks. Temporal guarantees that if a server crashes on step 4 of a 10-step agent plan, it resumes exactly at step 4 upon reboot.

### C. Stateless Workspaces: S3 / Object Storage
*   **Action:** Stop writing agent skills and deliverables to the local disk (`data/workspaces/`). 
*   **Why:** Local disks prevent horizontal scaling. All artifacts, deliverables, and agent context files must be streamed to an S3-compatible object store.

### D. The Diff Engine & Versioning
*   **Action:** Implement a strict versioning schema for Deliverables.
*   **Why:** When `POST /api/tasks/{id}/iterate` is called, the backend must *never* overwrite `v1`. It must generate `v2` and return the delta (additions/deletions) so the frontend can render the PR-style review UI.

### E. Hard Cost Circuit Breakers
*   **Action:** Implement a `max_budget_usd` on every execution wave.
*   **Why:** Without a human babysitting the nodes, the backend must strictly enforce token limits to prevent infinite hallucination loops from draining the Anthropic API balance.

---

## 6. Revised Data Model (High-Level)
The core entity shifts from the *Task* to the *Artifact*.

*   **`Project`**: The container (e.g., "Q3 Launch").
*   **`Artifact`**: The core entity (e.g., "Competitive Analysis.md" or "auth.ts").
    *   *Status*: `Drafting` -> `In Review` -> `Approved`.
*   **`ArtifactVersion`**: Tracks `v1`, `v2`, `v3`. Contains the S3 file pointer, token cost for this specific run, and the diff from the previous version.
*   **`ContextualComment`**: Replaces global task comments. Tied to a specific `ArtifactVersion` and a specific `text_highlight_range`. Triggers the next iteration.
*   **`ExecutionWave`**: The invisible backend worker thread that produces the `ArtifactVersion`.

---

## 7. Implementation Roadmap

**Phase 1: The Great Deletion & Database Migration (Weeks 1-2)**
*   Strip out WebSockets, Chat APIs, and Kanban logic.
*   Migrate JSON file storage to PostgreSQL + SQLAlchemy (async).
*   Move local ChromaDB to `pgvector`.

**Phase 2: The Smart Brief Engine (Week 3)**
*   Refine the `sufficiency-check` API to be lightning-fast (sub-2 seconds) and return exact string-matching coordinates for frontend highlighting.

**Phase 3: Artifact Versioning & Diffing (Weeks 4-5)**
*   Build the S3 integration for stateless workspaces.
*   Implement the `ArtifactVersion` data model.
*   Build the diffing utility to compare `v1` and `v2` text/code.

**Phase 4: Durable Execution (Weeks 6-7)**
*   Implement Temporal.io (or Celery) to handle the DAG execution.
*   Implement the "Auto-Assume" fallback for agents to prevent execution deadlocks.
*   Implement hard cost circuit breakers per Artifact.

---