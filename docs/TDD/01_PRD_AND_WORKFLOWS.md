# Phase 1 — Product Requirements & User Journeys

> **Document type:** Product Requirements Document (PRD)
> **Status:** Draft
> **Source of truth:** `docs/VISION_2.0.md`
> **Scope:** What the product does, who it is for, and the step-by-step user experience. No technical implementation details.

---

## 1. Product Overview

### One-Liner

> *You write the brief. We deliver the work. You review the diff.*

### What It Is

An **AI-powered autonomous agency** for code work. Users describe what they need in a structured brief, a cross-functional team of specialized AI agents collaborates to produce the deliverable, and the user reviews and iterates on the output through version-controlled diffs.

> **Current focus:** Code artifacts only. Prose/content/research artifact types are out of scope for the current implementation. The architecture supports multiple artifact types, but only code is actively developed and tested.

### Core Value Proposition

Unlike single-agent AI tools (Cursor, ChatGPT, Devin) that work in isolation, this product assembles **specialized agents that collaborate cross-functionally** — product, design, engineering, QA — like a real team. The designer informs the developer. The QA validates against the spec. Agents persist across projects and accumulate institutional knowledge, producing output that improves with every engagement.

### What It Is NOT

- **Not a chatbot.** There is no conversational interface for requesting work.
- **Not a task board.** There is no Kanban, no drag-and-drop status management.
- **Not a single-agent wrapper.** This is a multi-agent orchestration platform with parallel execution.

---

## 2. User Personas

### Persona 1: The Startup Founder

| Attribute | Detail |
|---|---|
| **Role** | Solo founder or founding team member (1-5 people) |
| **Core pain** | Wearing 10 hats. Needs content (pitch decks, competitive analyses, launch plans) AND code (features, landing pages, APIs) produced fast — without hiring a full team. |
| **What they do today** | Bounce between ChatGPT for writing, Cursor for code, Notion for planning. Each tool is siloed. The founder is the integration layer, manually transferring context between tools. |
| **What they want** | A single place where they describe what they need, and a team of specialists produces it — with design informing code, product informing content, QA catching gaps. |
| **Success metric** | Time from idea to deliverable drops from days to minutes. Output quality matches what a small agency would produce. |

**Day in the Life (with product):**
1. Morning — opens the app, creates a new deliverable: "Build a settings page with user preferences and notification controls."
2. Fills in the Smart Brief (goal, audience, tech stack context). Clicks **Validate**. Fixes one flagged issue (missing mobile responsiveness requirement). Clicks **Delegate**.
3. Sees the heartbeat UI — Step 1/4: Product Agent defining requirements... Step 2/4: Design Agent creating component specs... Grabs coffee.
4. Gets notification: "Deliverable Ready for Review." Opens the GitHub PR — sees product-informed, design-aligned code. Leaves one comment on spacing. The system pushes an updated commit.
5. Merges the PR. Total time invested: 12 minutes.

---

### Persona 2: The Product Manager

| Attribute | Detail |
|---|---|
| **Role** | PM at a seed-to-Series B startup (5-50 people) |
| **Core pain** | Needs both **strategic documents** (competitive analyses, PRDs, user research summaries) and **feature implementations** — but cannot bottleneck the engineering team with every spec, nor write every document themselves. |
| **What they do today** | Writes specs in Notion, drops them into Linear, waits for engineering. For content work, uses ChatGPT but spends 30+ minutes re-prompting to get the tone and depth right. |
| **What they want** | An AI team that understands their product deeply (persistent agents), produces research-backed deliverables, and iterates based on inline feedback — not "regenerate the whole thing." |
| **Success metric** | Reduces time spent on document creation by 80%. Feature specs include design and QA input before reaching engineering. |

**Day in the Life (with product):**
1. Creates a brief: "Write a competitive analysis of Notion, Coda, and Confluence — focus on enterprise pricing, collaboration features, and AI capabilities."
2. Clicks **Validate**. The system asks for target audience and desired output format. PM adds: "For the exec team, 3-5 pages, include a recommendation matrix." Clicks **Delegate**.
3. Heartbeat shows: Researching → Analyzing → Drafting → QA Review.
4. Opens the in-app review. Reads the analysis. Highlights the pricing section — "Add per-seat vs. flat-rate comparison." Comments on the conclusion — "Make the recommendation more decisive."
5. Sees `v2` with a red/green diff showing exactly what changed. Approves.

---

### Persona 3: The Agency Lead

| Attribute | Detail |
|---|---|
| **Role** | Runs a small digital agency or consulting firm (2-15 people) |
| **Core pain** | Needs to scale output across multiple clients without scaling headcount. Each client has different brand voice, tech stack, and domain knowledge. Hiring specialists for every competency is not economical. |
| **What they do today** | Manually briefs freelancers or junior team members. Reviews their output. Provides feedback. Waits for revisions. Repeat. The review-revision cycle is the bottleneck. |
| **What they want** | An AI team that learns each client's preferences, produces client-ready deliverables, and iterates instantly based on contextual feedback. The agency lead becomes a reviewer, not a doer. |
| **Success metric** | Can serve 3x more clients with the same headcount. First-draft approval rate exceeds 70%. |

**Day in the Life (with product):**
1. Switches to Client A's project. Creates a brief: "Write Q2 blog post about remote work productivity — match the brand voice from previous posts."
2. The Content Writer agent already knows Client A's tone (learned from 8 previous posts). The Research Agent has indexed Client A's industry reports.
3. Reviews `v1`. Only one highlight: "Soften the intro — Client A prefers questions over statements." Sees `v2` diff — just the intro changed. Approves.
4. Switches to Client B's project. Creates a code deliverable for an API endpoint. The Backend Dev agent knows Client B's FastAPI conventions from 4 previous features. Output matches their patterns without explicit instruction.

---

## 3. Core Concepts Glossary

| Concept | Definition |
|---|---|
| **Roster** | The user's persistent pool of specialized AI agents. Created during onboarding, customizable over time. Global scope — agents are shared across all projects. |
| **Agent** | A persistent AI entity with a specialization (e.g., "Product Expert", "Frontend Dev"), an isolated workspace, accumulated skills, and a learning profile. Agents are NOT disposable — they persist across projects and accumulate institutional knowledge. |
| **Agent Status** | `learning` → `ready` → `working` → `reflecting`. An agent must reach at least `partial` readiness before it can be auto-assembled into an execution team. Agents are set to `working` for the duration of each DAG slot and returned to `ready` when the slot completes. |
| **Progression Level** | `apprenti` (< 5 artifacts) → `opérationnel` (5-20 artifacts) → `expert` (20+ with high quality). Reflects the agent's maturity. |
| **Project** | A container for related work (e.g., "Q3 Product Launch", "Client A Website Redesign"). Has a published brief/context that all agents are briefed on. |
| **Artifact** | The core entity — a deliverable. Can be prose (markdown report, strategy doc) or code (feature implementation, API endpoint). One Artifact = one or many files (like a GitHub PR). Status: `Drafting` → `In Review` → `Approved` (+ `Cancelled`). |
| **ArtifactVersion** | An immutable snapshot of an Artifact at a point in time (v1, v2, v3...). Stores the file bundle (S3 directory), token cost, agent assumptions, sources used, and the computed diff from the previous version. Never overwritten. |
| **Brief** | The structured input a user provides to request a deliverable. Contains: Title, Goal, Target Audience, Context, Description. Must pass the Sufficiency Check before execution begins. |
| **Sufficiency Check** | A pre-flight LLM call that validates a brief for completeness and clarity. Triggered on "Validate" or "Delegate" click — not on every keystroke. Blocks submission if critical issues are found. |
| **ExecutionWave** | The invisible backend unit of work. Contains the DAG plan, the auto-assembled team (selected from the roster), agent assignments, and cost tracking. Produces one ArtifactVersion. |
| **DAG (Directed Acyclic Graph)** | The execution plan that determines which agents run in parallel (same wave) and which run sequentially (agents that depend on upstream outputs). Enables cross-functional collaboration. DAG templates now define three wave types: **planning** (leads analyze the brief and produce delegation plans), **execution** (workers implement their delegated tasks), and **review** (leads evaluate worker output and emit APPROVE / MINOR_FIX / REVISE decisions). |
| **ContextualComment** | A piece of user feedback tied to a specific text range within a specific ArtifactVersion. Triggers a targeted iteration — the agent rewrites only the highlighted section. |
| **Lead** | A roster agent with `role="lead"`. Leads plan work (analyze brief, produce delegation plan), delegate tasks to worker specialists, and review the outputs (`APPROVE` / `MINOR_FIX` / `REVISE`). Domain-specific: Tech Lead, PM Lead, Design Lead, Security Lead, DevOps Lead, Data Lead, Mobile Lead. |
| **Worker** | A roster agent with `role="worker"`. Workers execute the tasks delegated to them by leads and produce code files. |
| **Auto-Assembly** | The system's ability to read a brief and automatically select the right agents from the roster to form a team. Users can override but rarely need to. |
| **Auto-Resolution** | Agents never pause for human input during execution. They make safe assumptions, log them visibly, and continue. Users can override assumptions during review. |

---

## 4. User Journeys

### J1: First-Time Onboarding

**Trigger:** User signs up for the first time.

**Goal:** Get from signup to a working AI agency roster in under 5 minutes.

| Step | Screen / Action | System Behavior |
|---|---|---|
| 1 | **Welcome screen** — "Tell us about your company." | Displays a form: Company Name, Domain/Industry, Product Description, Company Stage, Target Audience, Main Goals, Existing Team Roles, Tech Stack, Team Size, Primary Use Case (content, code, or both), and optional context document uploads. |
| 2 | User fills in: *"B2B SaaS startup. Project management tool for engineers. Next.js + FastAPI + PostgreSQL. 3 people. Both code and content."* and optionally uploads a product spec or README. | — |
| 3 | User clicks **"Generate My Agency"** | Backend sends company context to LLM. LLM generates a tailored roster of 6-10 specialized agents based on the user's domain, stack, and use case. |
| 4 | **Roster Preview screen** — Shows the generated roster organized by category. | Displays each agent's name, specialization, and a one-line description. Categories: Product & Strategy, Engineering, Content & Research, Quality & Design. |
| 5 | User reviews the roster. Can: **rename** agents, **adjust** specializations (e.g., change "Content Writer" to "Technical Writer"), **add** custom agents (e.g., "Legal Compliance Reviewer"), or **remove** roles they don't need. | UI provides inline editing. Add Agent button opens a form: Name, Specialization, Description. |
| 6 | User clicks **"Confirm Roster"** | Backend creates all agent entities. Each agent enters `learning` status and begins its initial knowledge acquisition phase (web research on its specialization, indexing the company domain). |
| 7 | **Dashboard** — User sees their project list (empty) and the roster status panel showing agents in `learning` state with progress indicators. | Agents research autonomously in the background. Each agent's Knowledge Readiness score gradually increases: `insufficient` → `partial` → `sufficient`. |
| 8 | Agents reach `partial` readiness (typically 1-5 minutes). Status changes to `ready`. | User is notified: *"Your agency is ready. Create your first deliverable."* |

**Edge case — Impatient user:** If the user creates a deliverable before all agents are ready, the system only auto-assembles agents with `partial` or higher readiness. Under-prepared agents are excluded with a note: *"Research Analyst is still learning your domain. This deliverable will proceed without it."*

---

### J2: Creating a Prose Artifact

**Trigger:** User clicks **"New Deliverable"** from the project dashboard.

**Goal:** Go from an idea to a reviewed, approved document.

| Step | Screen / Action | System Behavior |
|---|---|---|
| 1 | **New Deliverable screen** — User selects artifact type: **Document** (prose) or **Code**. | Displays the Smart Brief form. |
| 2 | User fills in the Smart Brief form: | Form fields: **Title** (short name), **Goal** (what success looks like), **Target Audience** (who will read this), **Context** (background information, links, constraints), **Description** (detailed instructions). |
| 3 | *Example:* Title: "Q3 Competitive Analysis". Goal: "Identify top 3 competitor weaknesses we can exploit in messaging." Audience: "Exec team, Series A investors." Context: "Focus on US market, B2B SaaS only." Description: "Compare Notion, Coda, Confluence on pricing, collaboration, AI features. Include recommendation matrix." | — |
| 4 | User clicks **"Validate"** | Frontend sends the complete brief to `POST /api/briefs/sufficiency-check`. Backend runs a fast LLM call (< 3 seconds). |
| 5a | **If issues found:** UI displays inline issues with highlighted problem areas. | Example: *"Missing constraint: What time period for pricing data? Current or historical?"* The issue appears next to the relevant field with a yellow/red indicator. `critical` issues block submission. `warning` issues are advisory. |
| 5b | User fixes the flagged issues. Clicks **"Validate"** again. | New sufficiency check. If all critical issues resolved → green checkmark. |
| 6 | User clicks **"Delegate to Team"** | Backend: (1) Auto-assembles team from roster based on brief content. (2) Shows a confirmation listing the assembled agents and an estimated cost (based on template heuristics). User can override team selection. |
| 7 | User confirms delegation. | Artifact status → `Drafting`. Backend builds the DAG and begins execution. |
| 8 | **Heartbeat UI** — User sees high-level progress. | Steps displayed as human-readable labels mapped from DAG waves. Example: `Step 1/3: Researching competitors... ✅ Done` → `Step 2/3: Drafting analysis... ⏳ Now` → `Step 3/3: QA & compilation ○ Next`. Real-time cost counter. Estimated time remaining computed from elapsed time per step × remaining steps. |
| 9 | Execution completes. User receives notification: **"Deliverable Ready for Review."** | Artifact status → `In Review`. |
| 10 | **Review screen** — User opens the artifact. | Main panel: the full document (v1) rendered as rich text/markdown. Sidebar: **Sources** (URLs, documents the agents referenced), **Assumptions** (any decisions agents made autonomously, e.g., `[ASSUMPTION: US market only]`), **Cost** (total tokens and USD for this execution). |
| 11 | User reads the document. Wants changes to a specific section. | — |
| 12 | User **highlights** the pricing comparison paragraph. A comment box appears (inline, like Google Docs). Types: *"Add per-seat vs. flat-rate pricing breakdown."* Clicks **Submit Feedback**. | Backend receives the ContextualComment with `text_highlight_range` + comment text. Triggers a targeted iteration — only the highlighted section is rewritten. Artifact status → `Drafting` briefly. |
| 13 | Iteration completes. Artifact status → `In Review` again. | UI shows `v2`. A **diff toggle** lets the user switch between the full document view and a red/green diff view showing exactly what changed between v1 and v2. |
| 14 | User is satisfied. Clicks **"Approve"**. | Artifact status → `Approved`. Terminal state. The artifact is downloadable/exportable. Agents involved enter `reflecting` status (if reflection threshold is met) — extracting work learnings from this engagement. |

**Iteration loop:** Steps 12-13 can repeat as many times as needed. Each iteration produces a new ArtifactVersion (v3, v4...) with a diff from the previous version.

---

### J3: Creating a Code Artifact

**Trigger:** User clicks **"New Deliverable"** and selects **Code**.

**Goal:** Go from a feature description to a merged pull request.

| Step | Screen / Action | System Behavior |
|---|---|---|
| 1-7 | **Identical to J2** (Smart Brief → Validate → Delegate → Confirm). | Same flow. The brief form may include code-specific fields: Target Repository, Base Branch, Tech Stack (pre-filled from project/onboarding context). |
| 8 | **Heartbeat UI** — Same as J2 but with code-relevant step labels reflecting the three wave types. | **Planning phase (leads):** `Step 1/N: Tech Lead analyzing brief... ✅` → `Step 2/N: PM Lead producing delegation plan... ✅` → **Execution phase (workers):** `Step 3/N: Backend Dev implementing tasks... ⏳` → **Review phase (leads):** `Step N/N: Tech Lead reviewing output... ○`. The review cycle may repeat up to `max_iterations` times before force-finalize. |
| 8a | *(Internal — not visible to user)* **Planning phase:** Leads run first, analyzing the brief and producing a structured delegation plan via `## Specialist Delegation` sections. | Each lead agent writes which worker should handle which task with specific instructions. The orchestrator extracts these plans and injects them into each worker's prompt. |
| 8b | *(Internal)* **Execution phase:** Workers receive their delegated tasks from the planning phase and implement code files. | Workers produce files written into the artifact's S3 prefix. |
| 8c | *(Internal)* **Review phase:** Lead agents read all worker-produced files and emit a decision: `APPROVE`, `MINOR_FIX`, or `REVISE`. | `APPROVE` → finalize. `MINOR_FIX` → lead patches files directly with `file_write`. `REVISE` → per-specialist feedback extracted and injected for the next iteration loop. Multiple review leads run in parallel; consensus is `REVISE > MINOR_FIX > APPROVE`. |
| 9 | Execution completes (all leads approve or max_iterations reached). | **Divergence from J2:** The backend pushes the code to a **feature branch** on the connected GitHub/GitLab repository and opens a **Pull Request**. Artifact status → `In Review`. |
| 10 | User receives notification: **"Deliverable Ready for Review."** | The review screen shows: artifact metadata (title, cost, assumptions, sources) + a prominent **"View Pull Request on GitHub"** button linking to the PR. For code artifacts, there is NO in-app diff viewer — the user reviews code on GitHub/GitLab. |
| 11 | User clicks the link and reviews the PR on GitHub/GitLab. | Standard GitHub PR experience: multi-file diff, syntax highlighting, inline comments, CI checks. |
| 12a | **If the user leaves a PR comment on GitHub/GitLab:** | A webhook listener on the backend detects the PR comment/review event. The backend automatically triggers a targeted iteration — the relevant agent rewrites the flagged code. The system pushes an updated commit to the same PR branch. Artifact status briefly cycles: `Drafting` → `In Review`. |
| 12b | **If the user submits feedback through the in-app review screen (optional):** | Same behavior — targeted iteration, updated commit pushed to PR. |
| 13 | User is satisfied. **Merges the PR on GitHub/GitLab.** | The backend detects the merge event via webhook. Artifact status → `Approved`. Agents enter reflection if threshold met. |

**Key differences from J2:**
- Review happens on GitHub/GitLab, not in-app (outsourced to purpose-built code review UX).
- Iteration is triggered by PR comments (via webhook) in addition to in-app feedback.
- One Artifact may produce multiple files (like a real PR) — the ArtifactVersion stores a file bundle, not a single file.
- Approval happens when the PR is merged, not via an in-app button.

---

### J4: Managing the Agency Roster

**Trigger:** User navigates to **Settings → Agency Roster** (or clicks the Roster panel on the dashboard).

**Goal:** View, customize, and manage the persistent AI team.

| Step | Screen / Action | System Behavior |
|---|---|---|
| 1 | **Roster Overview screen** — Grid or list of all agents. | Each agent card shows: Name, Specialization, Status badge (`learning` / `ready` / `working` / `reflecting`), Progression Level badge (`apprenti` / `opérationnel` / `expert`), Knowledge Readiness score (0-100), Completed Artifacts count. |
| 2 | User clicks on an agent card (e.g., "Content Writer"). | **Agent Detail screen** — Full profile view. |
| 3 | **Agent Detail screen** shows: | **Profile tab:** Name, Specialization (editable), Description, Status, Progression Level, Model Tier (Sonnet/Opus — editable). |
| | | **Skills tab:** List of accumulated skill files — what the agent has learned. E.g., *"Brand voice: conversational, no corporate jargon"*, *"Prefers bullet-point recommendations over paragraph prose"*, *"Client A's target audience: enterprise CTOs."* |
| | | **History tab:** List of completed artifacts with quality indicators and dates. |
| | | **Knowledge tab:** Readiness score breakdown, knowledge recommendations (system-suggested research actions to fill gaps). |
| 4 | **Customize specialization:** User edits the specialization field. | E.g., changes "Content Writer" to "Technical Documentation Writer". This adjusts the agent's system prompt and future auto-assembly matching. |
| 5 | **View knowledge recommendations:** System has identified gaps. | Example: *"This agent should research React Server Components — 3 recent briefs referenced RSC but the agent has no indexed knowledge."* Two buttons: **Apply** (triggers targeted background research on the topic) or **Dismiss**. Recommendations are computed on-the-fly via a Haiku LLM call comparing recent workspace artifacts against the agent's current skill titles. |
| 6 | **Trigger manual research:** User clicks **"Research a Topic"** and types a topic. | E.g., *"WCAG 2.2 accessibility guidelines."* The topic is forwarded to the learning task as a targeted research prompt. The agent enters `learning` status, researches the specific topic (not a full workspace re-onboarding), and returns to `ready` when complete. |
| 7 | **Add a new agent:** User clicks **"Add Agent"** on the Roster Overview. | Form: Name, Specialization, Description. System creates the agent, enters `learning` phase. |
| 8 | **Archive an agent:** User clicks **"Archive"** on an agent card. | Soft removal — agent is hidden from the active roster and excluded from auto-assembly. All accumulated skills and learning are preserved. The agent can be restored via `POST /api/roster/{id}/restore`. |
| 9 | **Hard delete an agent:** User clicks **"Delete Permanently"** (requires confirmation). | Permanently removes the agent and all associated data (skills, learnings, workspace). Irreversible. Only available from the archive or via a danger-zone confirmation. |

---

### J5: Project & Brief Management

**Trigger:** User creates a new project or manages an existing one.

**Goal:** Organize work into projects with shared context that all agents are briefed on.

| Step | Screen / Action | System Behavior |
|---|---|---|
| 1 | **Dashboard** — User sees a list of their projects. | Each project card shows: Name, Description, number of artifacts, creation date. A **"New Project"** button. |
| 2 | User clicks **"New Project"**. | Form: Project Name, Description, Domain/Industry (optional — may inherit from account). |
| 3 | User creates: *"Q3 Product Launch"*. | Project created. User lands on the Project Dashboard showing an empty artifact list and a **Project Brief** section. |
| 4 | **Write the Project Brief:** User clicks **"Edit Brief"** in the Project Brief section. | Rich text editor for writing the project-level context. This is NOT a deliverable brief — it's the background context that all agents will be briefed on for every deliverable within this project. E.g., *"We're launching a new pricing tier for enterprise customers. Target market: US/EU. Key competitors: Notion, Coda. Our USP is real-time collaboration with AI assistance."* |
| 5 | User clicks **"Publish Brief"**. | Backend saves the published version and triggers **rebriefing** — all agents in the roster receive the project context as a skill file. SHA-256 fingerprint is stored for change detection. |
| 6 | **Rebriefing on updates:** User edits and re-publishes the project brief. | Backend detects the fingerprint mismatch. All agents are automatically rebriefed with the updated context. Previous briefing data is replaced (not stacked). |
| 7 | **Upload project documents:** User uploads PDFs, docs, URLs via the project's Document section. | Documents are ingested and indexed in the vector database. Relevant agents can retrieve this information during execution via semantic search. |
| 8 | **Create deliverables within the project:** User clicks **"New Deliverable"** from within the project. | Pre-fills the project context into the brief form. Agents auto-assembled for this deliverable already have the project brief loaded. |

---

### J6: Settings & Connections

**Trigger:** User navigates to **Settings**.

**Goal:** Configure external integrations and track usage.

| Step | Screen / Action | System Behavior |
|---|---|---|
| **Git Providers** | | |
| 1 | User clicks **"Connect GitHub"** (or GitLab). | User pastes a **Personal Access Token (PAT)**. No OAuth flow — AD-14 locks PAT-only for MVP. The backend validates the token immediately and stores it encrypted. |
| 2 | Connection established. | The connection is workspace-scoped. The target repository URL is specified per code artifact (in the Smart Brief). |
| 3 | User can test the connection. | Backend calls the provider API with the stored PAT and reports success/failure. |
| **MCP Connections** | | |
| 4 | User clicks **"Add MCP Connection"**. | Form: Connection Name, Server URL, Authentication (API key, OAuth). MCP = Model Context Protocol — allows agents to call external tools (Notion, Slack, custom APIs). |
| 5 | User adds a Notion connection. | Backend discovers available tools on the MCP server. User sees: *"Available tools: read_page, create_page, search."* |
| 6 | MCP connections are bound at the **project or team level**, not per-agent. | All agents auto-assembled for a project can use the project's MCP connections. No per-agent IT admin work. |
| **Usage & Cost Tracking** | | |
| 7 | User navigates to **"Usage"** tab. | Dashboard showing: total tokens consumed, cost breakdown by model (Sonnet vs. Opus), cost per artifact, daily/weekly/monthly trends, budget ceiling settings. |
| 8 | User sets a **monthly budget ceiling.** | Backend enforces hard circuit breakers. If the ceiling is approached, a warning is shown. If exceeded, new executions are blocked until the next billing cycle or the user raises the limit. |

---

## 5. Artifact State Machine

### States

| State | Description | Who is acting |
|---|---|---|
| **Drafting** | The AI team is executing the DAG. The user sees a heartbeat progress UI. | System (agents) |
| **In Review** | Execution complete. The artifact (prose or code PR) is ready for the user to review. | Human |
| **Approved** | The user accepted the deliverable. Terminal state. | — |
| **Cancelled** | The artifact was cancelled by the user. Terminal state. | — |

### Transitions

```
                    ┌────────────────────────────────┐
                    │                                │
                    ▼                                │
┌───────────┐    ┌───────────┐    ┌───────────┐     │
│  DRAFTING │───▶│ IN REVIEW │───▶│  APPROVED │     │
└─────┬─────┘    └─────┬─────┘    └───────────┘     │
      │                │                             │
      │                │  User requests iteration    │
      │                └─────────────────────────────┘
      │                │
      │                ▼
      │          ┌───────────┐
      └─────────▶│ CANCELLED │
                 └───────────┘
                       ▲
                       │
              (also reachable from In Review)
```

| Transition | Trigger | Description |
|---|---|---|
| → **Drafting** | User clicks "Delegate to Team" | Initial creation. Backend builds DAG, auto-assembles team, begins execution. |
| **Drafting** → **In Review** | Execution completes | All DAG waves finished. Artifact version is ready for human review. |
| **In Review** → **Drafting** | User submits contextual feedback (highlight + comment) or PR comment detected via webhook | Targeted iteration — agent rewrites only the relevant section/code. Produces a new ArtifactVersion. |
| **In Review** → **Approved** | User clicks "Approve" (prose) or merges the PR (code) | Terminal state. Deliverable is done. Agents may enter reflection. |
| **Drafting** → **Cancelled** | User cancels during execution | Soft cancel: execution is halted, artifact is archived with all existing versions preserved. |
| **In Review** → **Cancelled** | User cancels during review | Soft cancel: artifact is archived. Existing versions remain accessible for reference. |
| **Cancelled** → *(hard delete)* | User permanently deletes from archive | Irreversible. All versions, comments, and execution data are removed. Requires explicit confirmation. |

### Rules

1. **No skipping states.** An artifact cannot go from `Drafting` directly to `Approved` — execution must complete and the human must review.
2. **ArtifactVersions are immutable.** Iteration creates a new version (v2, v3...), never overwrites v1. The diff between versions is always available.
3. **Cancelled is soft by default.** The artifact is archived (hidden from active views) but all history is preserved. Hard delete is a separate, explicit action.
4. **The only loop is Review → Drafting → Review.** This can repeat indefinitely until the user approves or cancels.
5. **Code artifacts have an external approval trigger.** For code artifacts, "Approved" is triggered by merging the PR on GitHub/GitLab (detected via webhook), not by an in-app button click.

---

## 6. Edge Cases & Error Flows

### 6.1 Brief Validation Failure

| Scenario | System Behavior |
|---|---|
| User clicks "Validate" with a vague brief | Sufficiency check returns `eligible: false` with specific issues. UI highlights problem areas inline. `critical` issues block submission. `warning` issues are advisory. |
| User clicks "Delegate" without validating first | The system runs the sufficiency check automatically before execution begins. If critical issues found, delegation is blocked — same UI as clicking "Validate". |
| Sufficiency check API times out (> 5 seconds) | UI shows: *"Validation is taking longer than expected. Please try again."* User can retry or proceed with a warning that the brief was not validated. |

### 6.2 Execution Failure / Timeout

| Scenario | System Behavior |
|---|---|
| An agent fails mid-execution (LLM error, API timeout) | The failed slot is retried up to 3 times with exponential backoff (2s, 4s, 8s). If all retries fail, the DAG execution fails, the wave status → `failed`, and the artifact remains in `Drafting`. The user can retry via `POST /api/artifacts/{id}/retry`, which creates a new `ExecutionWave` from the failed wave's DAG plan. |
| The entire execution wave times out (10-minute soft limit) | The Celery soft time limit fires. Wave status → `failed` with `error_message = "Execution timed out"`. Artifact remains in `Drafting`. User can retry via `POST /api/artifacts/{id}/retry`. |
| Orphaned artifact — stuck in `Drafting` with no active execution process (e.g., after server crash) | A background reaper (`reap_orphaned_waves`) runs every 2 minutes and marks waves stuck in `running` for > 10 minutes as `failed`. The artifact remains in `Drafting` with a failed wave. |

### 6.3 Cost Ceiling Hit

| Scenario | System Behavior |
|---|---|
| An execution wave approaches the per-artifact budget ceiling | The circuit breaker halts execution before exceeding the limit. Artifact enters error state. User is notified: *"Budget limit reached ($X.XX / $Y.YY). You can increase the limit and retry, or approve the partial output."* |
| Monthly account budget ceiling reached | New executions are blocked. User sees: *"Monthly budget ceiling reached. Increase your limit or wait until [next billing date]."* Existing artifacts in review are unaffected. |

### 6.4 GitHub/GitLab Push Failure

| Scenario | System Behavior |
|---|---|
| Push to feature branch fails (auth expired, repo deleted, branch conflict) | Artifact stays in `Drafting` with an error: *"Failed to push to GitHub: [reason]."* User is prompted to check their Git connection in Settings. Retry button available. |
| PR creation fails | Same as above. The code artifact still has its files stored in S3 — the user can download them manually as a fallback. |
| Webhook delivery fails (GitHub doesn't send the event) | If a PR comment is missed, the user can manually submit feedback through the in-app review screen to trigger iteration. **Note:** Backend webhook polling fallback is not implemented. |
| PR merge event not detected | The user can manually click "Approve" in the in-app review screen to transition the artifact to `Approved`. **Note:** Automatic polling for merge status is not implemented. |

### 6.5 Agent Not Ready

| Scenario | System Behavior |
|---|---|
| Auto-assembly selects an agent that is still in `learning` status | The agent is excluded from the team. The system proceeds with the available agents and informs the user: *"Research Analyst is still learning your domain. This deliverable will proceed without it."* |
| All agents needed for a brief are in `learning` status | Execution is blocked. User is informed: *"Your agents are still learning. Estimated time to readiness: ~X minutes."* User can wait or manually trigger faster learning. |
| An agent enters `reflecting` status during auto-assembly | Reflection is non-blocking for assembly. The agent's current skills (pre-reflection) are used for execution. Reflection continues in the background and will be available for the next execution. |

### 6.6 Concurrent Execution Conflicts

| Scenario | System Behavior |
|---|---|
| Two artifacts need the same agent simultaneously | **Parallel execution is safe.** Agents are stateless during execution — they read their skills/workspace at the start and write to an isolated, artifact-specific scratchpad. Two artifacts using the same agent profile execute independently with no shared mutable state. |
| Two agents finish reflection at the same time | **Sequential reflection with DB locks.** The reflection phase writes to the agent's persistent workspace (skills, work learnings). To prevent race conditions, reflection acquires a database-level lock on the agent record. The second reflection waits until the first completes. |

### 6.7 Webhook Delivery Failure

| Scenario | System Behavior |
|---|---|
| GitHub/GitLab webhook not configured | User is prompted during Git provider setup to install the webhook. If skipped, PR-based iteration falls back to manual: user must submit feedback through the in-app review screen. |
| Webhook payload is malformed or from an unknown PR | Backend validates the payload (signature verification, PR ID matching). Malformed or unknown payloads are logged and discarded. No user impact. |
| Webhook arrives for a PR that has already been approved/cancelled | Backend ignores the event. Artifacts in terminal states (`Approved`, `Cancelled`) do not accept new iterations. |

---

## 7. Out of Scope for MVP

The following features are explicitly **deferred** to post-MVP releases. They are not forgotten — they are intentionally excluded to keep the initial scope manageable.

| Feature | Reason for Deferral |
|---|---|
| **Real-time collaborative editing** (multiple users editing an artifact simultaneously) | Adds significant complexity (OT/CRDT). Single-reviewer model is sufficient for MVP target users (small teams, solo founders). |
| **Agent-to-agent chat / visible inter-agent communication** | Agents communicate via the DAG (upstream outputs flow to downstream agents). Exposing this to the user adds noise without adding value for MVP. |
| **Custom DAG design** (user manually wires which agents connect to which) | Auto-assembly + DAG generation handles 90% of cases. Power-user DAG editing is a post-MVP feature. |
| **Multi-tenant / team workspaces** (multiple human users sharing one roster) | MVP targets individual users. Team features (roles, permissions, shared roster) come later. |
| **Billing & payments** | MVP is invite-only / beta. Users bring their own API keys or are on a flat-rate pilot. Payment integration is post-MVP. |
| **Mobile app** | Web-first. Mobile is deferred. |
| **Self-hosted deployment** | Cloud-only for MVP. Self-hosted option (for enterprises with data sovereignty needs) is post-MVP. |
| **Agent marketplace / templates** | Sharing agent configurations or pre-built specialists across users. Deferred to post-MVP community features. |
| **Scheduled / recurring artifacts** | "Generate this competitive analysis every month." Valuable but adds scheduling complexity. Deferred. |
| **Branching artifacts** (fork a v2 into two parallel v3 variants) | Useful for A/B content testing. Deferred. |
| **Audit log / compliance reporting** | Enterprise feature. Deferred. |
