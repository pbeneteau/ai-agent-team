# Vision 2.0 — The Artifact-First Orchestrator

> **One-liner:** You write the brief. We deliver the work. You review the diff. — The AI agency for knowledge work and code. Specialized agents collaborate cross-functionally — product, design, engineering, QA — like a real team, not a single chatbot.

---

## 1. Executive Summary

### The Problem with V1

V1 tried to be two products at once:

1. **A conversational chatbot (Alex)** — assuming the user wants an unstructured, "do it for me" relationship.
2. **A Linear/Jira-style task board (9-state Kanban)** — assuming the user wants granular, deterministic micromanagement.

These paradigms are at war. If Alex is smart enough to build a team and execute a plan, why does the human need to manually drag a Kanban card from "Executing" to "Review"? The result: a system that generated *more* work for the PM, not less. Notification fatigue, review bottlenecks, `input_needed` deadlocks, and a debugging nightmare when outputs were poor.

### The Pivot

We abandon both the "Chatbot" and the "Jira for Bots" paradigms entirely.

We shift to the **Artifact-First Model** (internally: "The Pull Request Model"). Humans do not want to manage the *process* of AI — they want to review the *outcomes*. Our product is no longer a chat interface or a task board. It is an **Autonomous Agency**. The user provides a validated brief, the AI workforce executes in parallel behind the scenes, and the system delivers a version-controlled artifact for human review and contextual iteration.

---

## 2. The Agency — Persistent Roster & Auto-Assembly

The user does not manually create agents or teams per deliverable. Instead, they have a **persistent agency** — a roster of specialized agents that the system assembles into teams automatically based on each brief.

### Onboarding (First-Time Setup)

When a user signs up, they go through a lightweight onboarding flow:

1. **Describe your company/domain:** "We're a B2B SaaS startup building a project management tool. Stack: Next.js, Python/FastAPI, PostgreSQL."
2. **The system generates a default roster** of agents tailored to their context:

```
┌─────────────────────────────────────────────────────────┐
│                   YOUR AGENCY ROSTER                    │
│                                                         │
│  Product & Strategy          Engineering                │
│  ┌─────────────────┐        ┌─────────────────┐       │
│  │ Product Expert   │        │ Frontend Dev     │       │
│  │ Strategy Analyst │        │ Backend Dev      │       │
│  └─────────────────┘        │ Full-Stack Dev   │       │
│                              └─────────────────┘       │
│  Content & Research          Quality & Design           │
│  ┌─────────────────┐        ┌─────────────────┐       │
│  │ Content Writer   │        │ Design Expert    │       │
│  │ Research Analyst │        │ QA Engineer      │       │
│  └─────────────────┘        └─────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

3. **The user confirms or customizes.** They can rename agents, adjust specializations, add domain-specific agents (e.g., "Legal Compliance Reviewer"), or remove roles they don't need.

### Auto-Assembly (Per Brief)

When the user submits a brief, they do NOT pick a team. The system reads the brief and **auto-selects** the right agents from the roster:

| Brief | Auto-Assembled Team |
|---|---|
| "Build a settings page with user preferences" | Product Expert → Design Expert → Frontend Dev → QA Engineer |
| "Write a competitive analysis of 3 SaaS competitors" | Research Analyst → Strategy Analyst → Content Writer |
| "Create a REST API for user authentication" | Product Expert → Backend Dev → QA Engineer |
| "Write a launch plan with landing page copy" | Strategy Analyst → Content Writer → Design Expert |

The user sees a brief confirmation before execution: *"This will be handled by: Product Expert, Design Expert, Frontend Dev, QA Engineer. Estimated cost: ~$0.85."* They can override the team selection, but 90% of the time auto-assembly is correct.

### Persistent Learning Across Projects

Because agents are **persistent** (not created/destroyed per brief), they accumulate institutional knowledge:

- The **Design Expert** learns your design system, preferred component library, and spacing conventions after the first few projects.
- The **Content Writer** learns your brand voice, tone preferences, and the corrections you commonly make.
- The **Backend Dev** learns your API conventions, error handling patterns, and tech stack specifics.
- The **Product Expert** learns your product's domain, user personas, and strategic priorities.

Each agent's workspace persists between briefs. Skills, reflections, and work learnings compound over time. **This is the moat** — the longer a user stays, the better their agency gets.

### Roster Management (Settings Page)

Users can manage their roster at any time:

- **View agents:** See each agent's specialization, accumulated skills, and project history
- **Customize specialization:** Adjust an agent's focus (e.g., make the Content Writer specialize in technical documentation)
- **Add agents:** Create new specialists for niche roles (e.g., "SEO Specialist", "Data Analyst")
- **Archive agents:** Remove agents no longer needed (preserving their learned skills in case they're restored)
- **View learning:** See what each agent has learned — skills, preferences, domain knowledge

### What This Replaces from V1

In V1, team/agent creation happened through conversational chat with Alex ("Hey Alex, create a marketing team with 3 specialists"). This was killed because:
- Chat is a slow, error-prone way to configure a system
- It conflated two different tasks: configuration (rare) vs. execution (frequent)

The roster model separates these cleanly:
- **Configuration** (rare): Onboarding + roster management settings page
- **Execution** (frequent): Smart Brief → auto-assembly → black box → review

---

## 3. Agent Lifecycle — Spawn, Learn, Execute, Reflect

Agents are not disposable prompt wrappers. They are persistent entities with a lifecycle that mirrors a real employee: they onboard, learn the domain, execute work, and improve over time.

### Agent Statuses

| Status | Description |
|---|---|
| `learning` | Initial knowledge acquisition in progress (onboarding, research, document ingestion) |
| `ready` | Has sufficient knowledge, available for assignment to execution waves |
| `working` | Currently executing within a DAG wave |
| `reflecting` | Post-execution learning consolidation (extracting work learnings, updating skills) |

### Phase 1: Spawning & Initial Learning

When an agent is added to the roster (during onboarding or manually), it enters the `learning` phase. This is an automated, multi-step knowledge acquisition process:

```
Agent Created
     │
     ▼
┌─────────────────────────────────────────────┐
│              LEARNING PHASE                 │
│                                             │
│  1. Receive Project Brief                   │
│     (company context, domain, stack, goals) │
│                                             │
│  2. Autonomous Web Research                 │
│     (searches its specialization domain,    │
│      reads articles, indexes findings)      │
│                                             │
│  3. Document Ingestion                      │
│     (uploaded PDFs, docs, URLs →            │
│      semantic indexing in pgvector)         │
│                                             │
│  4. Generate Initial Skills                 │
│     (markdown files capturing what it       │
│      learned about the domain)             │
│                                             │
│  5. Knowledge Readiness Scoring             │
│     insufficient → partial → sufficient     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
          Agent status → `ready`
          (available for execution)
```

**Gate:** An agent does not participate in execution waves until its knowledge readiness score is at least `partial`. The system will not auto-assemble an under-prepared agent into a team.

### Phase 2: Execution (During DAG Waves)

When the system auto-assembles a team for a brief, the selected agents enter `working` status. During execution, agents have access to all their tools (see below) and their accumulated skills are loaded into context.

### Phase 3: Post-Execution Reflection

After an artifact is approved (or after a configurable number of completed executions), the agent enters `reflecting` status and runs an automated reflection cycle:

1. **Extract Work Learnings** — What went well? What did the user correct? What sources were useful?
2. **Update Skills** — Consolidate new learnings into existing skill files
3. **Core Skills Compaction** — When skill files exceed a size threshold, the agent consolidates them into a tighter, higher-signal summary
4. **Update Progression Level** — Based on completed artifacts, quality scores, and user corrections:
   - `apprenti` — Fewer than 5 completed artifacts, still calibrating
   - `opérationnel` — 5-20 completed artifacts, reliable output
   - `expert` — 20+ completed artifacts with consistently high quality scores

### Agent Tool Capabilities

Agents are not limited to text generation. They have access to a tool suite that lets them research, read code, interact with external systems, and produce grounded outputs.

| Tool | Description | Available During |
|---|---|---|
| **Web Search** | Search the web via Serper API — competitor research, fact-checking, market data | Learning, Execution |
| **Web Browser** | Deep-read web pages, scrape structured data, follow links | Learning, Execution |
| **Vector DB Search** | Semantic search across all indexed documents (pgvector) | Learning, Execution |
| **File Read/Write** | Read and write files in the agent's isolated workspace | Learning, Execution, Reflection |
| **Document Ingestion** | Index uploaded files (PDF, DOCX, TXT, MD, CSV, JSON, YAML) into vector DB | Learning |
| **MCP Connections** | Call external tools via Model Context Protocol (Notion, Slack, custom APIs) | Execution |
| **Git Providers** | Clone repos, read code, push approved artifacts, open PRs (GitHub/GitLab) | Execution |

**Important:** MCP connections and Git providers are bound at the **project or team level**, not per-agent. This avoids the V1 anti-pattern of forcing users to act as IT admins for individual bots.

### Knowledge Lifecycle

Knowledge is not static. It evolves through a continuous cycle:

```
                    ┌──────────────┐
                    │ Project Brief│
                    │ Published    │
                    └──────┬───────┘
                           │ Briefing
                           ▼
┌──────────┐      ┌──────────────┐      ┌──────────────┐
│ Document │─────▶│    Agent     │─────▶│  Execution   │
│ Uploaded │ Ingest│   Skills    │ Load  │  (DAG Wave)  │
└──────────┘      │   (Workspace)│       └──────┬───────┘
                  └──────▲───────┘              │
                         │                      │ Work Learnings
                         │ Consolidate          │
                  ┌──────┴───────┐              │
                  │  Reflection  │◀─────────────┘
                  └──────────────┘
                         │
                         │ Brief changes detected
                         │ (fingerprint mismatch)
                         ▼
                  ┌──────────────┐
                  │  Rebriefing  │
                  │  (automatic) │
                  └──────────────┘
```

| Event | What Happens |
|---|---|
| **Briefing** | Project context is injected as a skill file when the brief is published. All roster agents receive it. |
| **Rebriefing** | When the project brief changes (detected via SHA-256 fingerprint), all agents are automatically rebriefed with the updated context. |
| **Work Learnings** | After each completed artifact, the system extracts insights: useful sources, effective approaches, user corrections, domain facts. Saved as skill files. |
| **Reflection** | Periodic consolidation (after N completed artifacts or on a timer). The agent reviews all recent learnings and updates its core skills. Noisy or redundant learnings are compacted. |
| **Knowledge Recommendations** | The system audits each agent's knowledge readiness and suggests actions to fill gaps (e.g., *"This agent should research React Server Components"*). Can be auto-applied (triggers web research) or dismissed. |

### Learning Triggers

| Trigger | When |
|---|---|
| Agent creation | During onboarding or when manually added to roster |
| Project brief published/updated | Automatic rebriefing of all agents |
| Document uploaded to project | Ingested and indexed, relevant agents notified |
| Artifact completed | Work learnings extracted from execution |
| Periodic reflection | Configurable interval (e.g., every 5 completed artifacts) |
| Manual research request | User triggers research on a specific topic for a specific agent |
| Knowledge recommendation applied | User approves a system-suggested research action |

---

## 4. The Core Product Loop — "Brief-to-PR" Pipeline

The entire user experience is reduced to four polished, frictionless steps:

```
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 │  1. SMART    │     │  2. BLACK    │     │  3. PULL     │     │  4. CONTEXT  │
 │    BRIEF     │────▶│    BOX       │────▶│   REQUEST    │────▶│   ITERATION  │
 │  (Input)     │     │ (Execution)  │     │  (Review)    │     │   (Diffs)    │
 └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
   Smart Form           Autonomous           Document/Code         Highlight +
   + Sufficiency         DAG Execution        Editor UI             Comment =
   Check                 (invisible)          + Sources/             Targeted
                                              Assumptions            Rewrite
```

### Phase 1: The Smart Brief (Input)

The user clicks **"New Deliverable"** and is presented with a clean, structured form: Title, Goal, Target Audience, Context, Description.

**The Pre-flight Model:** The sufficiency check is NOT a real-time keystroke debounce (that would burn API tokens on every edit and create race conditions). Instead, when the user clicks **"Delegate"** or **"Validate"**, the frontend sends the complete brief to the `sufficiency-check` API as a single pre-flight call.

- If the brief passes: execution begins immediately.
- If the brief is vague: the API returns specific issues, the UI displays them inline, and submission is **blocked** until the user fixes them.

**Example flow:**
1. User writes: *"Write a competitive analysis."* and clicks **Validate**.
2. The UI displays: *"Missing constraints: Which competitors? US or EU market? What dimensions (Pricing, UX, Features)?"* with highlighted problem areas.
3. User refines the brief, clicks **Validate** again. Green light. Clicks **Delegate to Team**.

**Why this matters:** We force the human to write a perfect spec *before* a single Anthropic token is spent on execution. The pre-flight model keeps costs predictable (one LLM call per validation, not hundreds per typing session) while still guaranteeing agents receive an unambiguous brief.

### Phase 2: The Black Box with Heartbeat (Execution)

Once the brief passes validation, the user clicks **"Delegate to Team"**. The backend takes the spec, builds the DAG, auto-assembles the team from the roster, and executes the work in parallel waves.

There is no Kanban board, no node-level micromanagement. But the user is NOT staring at a blind spinner for 5 minutes either. The UI displays a **high-level progress heartbeat**:

```
┌─────────────────────────────────────────────────┐
│  Competitive Analysis — Delegated to Team       │
│                                                 │
│  ✅ Step 1/4: Researching competitors...  Done  │
│  ✅ Step 2/4: Analyzing pricing data...   Done  │
│  ⏳ Step 3/4: Drafting report...          Now   │
│  ○  Step 4/4: QA & compilation            Next  │
│                                                 │
│  Estimated time remaining: ~2 min               │
│  Cost so far: $0.42                             │
└─────────────────────────────────────────────────┘
```

Each DAG wave maps to a human-readable step. The backend streams lightweight status updates (via SSE or polling) so the user has confidence the system is working without needing to understand the internal DAG structure.

**Auto-Resolution:** If an agent hits an ambiguity during execution, it does NOT pause and wait. It makes a safe assumption, logs it visibly in the deliverable (e.g., `[ASSUMPTION: US Market only]`), and keeps moving. The user can override assumptions during review.

### Phase 3: The Pull Request (Review)

The user receives a notification: **"Deliverable Ready for Review."**

They open a clean Document/Code Editor UI showing the actual artifact (`v1`). A sidebar displays:
- **Sources** the agents used (URLs, documents, data)
- **Assumptions** the agents made during execution
- **Cost** of this execution run

The user is not reviewing a task ticket — they are reviewing the work product itself.

### Phase 4: Contextual Iteration (Diffs)

If the user wants changes, they do NOT go to a global chat box. Instead:

1. The user **highlights** a specific paragraph or code block.
2. A comment box appears (like Google Docs or Notion).
3. The user types: *"Make this section more aggressive and focus on enterprise pricing."*
4. The backend triggers a **targeted iteration**. The agent rewrites *only* that section.
5. The UI updates to `v2`, showing a standard **red/green visual diff** of exactly what changed.

This is **Contextual Chat** — feedback is always attached to a specific piece of the artifact, never floating in a disconnected global thread.

---

## 5. The Core Differentiator — Cross-Functional Agent Collaboration

This is the single most important architectural decision and what separates us from every competitor.

### The Problem with Every AI Tool Today

Every coding agent (Cursor, Devin, Copilot) works **alone**. A coding agent receives an issue description and writes code in isolation. It never consults a product expert about user flows. It never asks a design expert about component hierarchy, spacing, or accessibility. It never checks with a QA expert about edge cases.

In a real agency, the designer talks to the developer. **In every AI tool today, they don't.**

### How Our DAG Enables Cross-Functional Collaboration

When a user submits a brief like "Build a settings page", the system doesn't hand it to a single coding agent. It builds a DAG where specialized agents collaborate:

```
User Brief: "Build a settings page"

┌─────────────────────────────────────────────────────────┐
│                    EXECUTION DAG                        │
│                                                         │
│  Wave 1 (parallel):                                     │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │ Product Agent   │  │ Design Agent    │              │
│  │ • User flows    │  │ • Component     │              │
│  │ • Requirements  │  │   hierarchy     │              │
│  │ • Edge cases    │  │ • Spacing/a11y  │              │
│  │ • Acceptance    │  │ • Design tokens │              │
│  │   criteria      │  │ • Responsive    │              │
│  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                         │
│           ▼                    ▼                         │
│  Wave 2:                                                │
│  ┌─────────────────────────────────────┐               │
│  │ Code Agent                          │               │
│  │ • SEES product agent's requirements │               │
│  │ • SEES design agent's component     │               │
│  │   specs, tokens, accessibility      │               │
│  │ • Writes implementation informed    │               │
│  │   by both                           │               │
│  └────────────────┬────────────────────┘               │
│                   │                                     │
│                   ▼                                     │
│  Wave 3:                                                │
│  ┌─────────────────────────────────────┐               │
│  │ QA Agent                            │               │
│  │ • Validates against product specs   │               │
│  │ • Validates against design specs    │               │
│  │ • Checks edge cases & accessibility │               │
│  └─────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
```

**The code agent doesn't guess** what the component should look like. It receives explicit design specs from the Design Agent and explicit requirements from the Product Agent. The QA Agent validates against both. This is why our output quality is structurally better than single-agent tools.

### This Works for Content Too

```
User Brief: "Write a competitive analysis of our SaaS vs. 3 competitors"

Wave 1 (parallel):
  ├── Research Agent → scrapes competitor pricing, features, reviews
  ├── Data Agent → pulls usage metrics, market share data
  └── Product Agent → defines analysis framework, key dimensions

Wave 2:
  └── Strategy Agent → writes the analysis using all three inputs
       (SEES the data, the research, AND the framework)

Wave 3:
  └── Editor Agent → reviews for clarity, consistency, missing gaps
```

### Why Competitors Can't Do This

| Competitor | Limitation |
|---|---|
| **Cursor / Devin / Copilot** | Single coding agent. No cross-functional input. Writes code from a text description alone. |
| **Linear Next** | Orchestrates third-party agents, but those agents **don't talk to each other**. Cursor doesn't see ChatPRD's output. They're siloed. |
| **Claude / ChatGPT** | One model, one context window. Can play multiple "roles" but it's still one brain — no true specialization or parallel execution. |
| **CrewAI / AutoGen** | Frameworks, not products. Developer must build the orchestration. No end-user UX. |

---

## 6. Competitive Positioning

### vs. Claude / ChatGPT

| Dimension | Claude / ChatGPT | Our Product |
|---|---|---|
| **Execution Model** | One smart intern, one context window, sequential | Multi-agent team, parallel specialist execution via DAG |
| **Output Format** | Chat bubbles in a stream | Version-controlled Artifacts with visual diffs |
| **Iteration UX** | "Rewrite the whole thing" in a new chat bubble; user re-reads everything | Highlight a section, comment, see a targeted diff of only what changed |
| **Memory** | Stateless (limited to uploaded files per conversation) | Persistent agent workspaces with accumulated skills and institutional knowledge |
| **Cross-functional** | One model pretending to be multiple roles | Actual specialized agents collaborating via DAG |
| **Quality Control** | Read the whole output and hope nothing changed | PR-style review with sources, assumptions, and diffs |

### vs. Linear Next + Coding Agents (Cursor, Devin)

| Dimension | Linear Next | Our Product |
|---|---|---|
| **Agent workforce** | Delegates to third-party agents (Cursor, Devin, Copilot) — middleman | Built-in multi-agent teams with persistent learning |
| **Cross-functional collaboration** | Agents are siloed — Cursor doesn't see ChatPRD's output | Agents share context within the DAG — Code Agent sees Design Agent's specs |
| **Content deliverables** | Code-only (PRs, fixes). No reports, strategies, analyses | Code AND content — unified artifact treatment |
| **Input quality** | No spec validation — assign issue and hope | Smart Brief with real-time sufficiency check |
| **Review UX** | Review in GitHub (external) | In-product review with highlight → comment → targeted diff |
| **Agent memory** | Stateless — Cursor starts fresh every time | Agents accumulate institutional knowledge across projects |
| **Setup cost** | Must configure Cursor + Devin + Copilot + Sentry separately | Self-contained — zero integrations needed |

### The Pitch

> *"You write the brief. We deliver the work. You review the diff."*
>
> *Every AI coding tool gives you a single agent working alone. We give you a cross-functional team — product, design, engineering, QA — that collaborates on every deliverable. The designer informs the developer. The QA validates against the spec. Like a real agency, except it runs in minutes and learns from every project.*

---

## 7. Unifying Code and Content

This architecture treats **all work as Artifacts (Files)**. Whether agents write a Python script or a Marketing Strategy, the backend handles it identically.

### General Tasks (Research, Strategy, Content)

- **Input:** Smart Form with sufficiency check
- **Output:** Markdown/Rich Text file (e.g., `launch-plan.md`)
- **Review:** In-app prose diff viewer (e.g., `react-diff-viewer-continued`) — red strikethroughs, green additions
- **Iteration:** Highlight text → comment → targeted rewrite → see diff in-app
- **Delivery:** Download, export, or publish

### Code Tasks (Features, Scripts, Bug Fixes)

- **Input:** Smart Form with sufficiency check (e.g., *"Which database? Which auth providers?"*)
- **Output:** Code files (e.g., `/api/auth/[...nextauth].ts`)
- **Review:** We do NOT build a custom code diff UI. Instead, the backend pushes the code to a **feature branch** and opens a **Pull Request** on GitHub/GitLab. The user reviews the code diff using GitHub/GitLab's native PR interface — which is already world-class.
- **Iteration:** The user leaves PR comments on GitHub/GitLab. The backend picks up the feedback, triggers a targeted iteration, and pushes updated commits to the same PR.
- **Delivery:** Merge the PR on GitHub/GitLab

### Two Review Tracks

| Artifact Type | Diff Strategy | Review Surface |
|---|---|---|
| **Prose/Markdown** | In-app diff viewer (`react-diff-viewer-continued`) | Our product UI |
| **Code** | GitHub/GitLab Pull Request | GitHub/GitLab native UI |

This is a pragmatic decision: GitHub/GitLab have spent years perfecting code review UX (syntax highlighting, inline comments, multi-file diffs, CI checks). We don't need to rebuild it. We own the prose review experience; we outsource code review to the tools developers already use.

### Why Still Unified Under the Hood

1. **Unified Storage:** Both code and text are files in agent workspaces.
2. **Unified Execution:** The DAG and agent tools work identically regardless of content type.
3. **Unified Tooling:** Agents use the same tools (`file_read`, `file_write`, `workspace_list`) for code and prose.
4. **Divergent Review:** Only the review surface differs — in-app for prose, GitHub/GitLab for code.

### Sandbox Rule for Code

Agents write code to their **isolated workspace only** — never directly to the production codebase. The backend pushes to a feature branch and opens a PR. The user merges when satisfied.

---

## 8. What Was Killed from V1

To achieve this vision, the following V1 features were removed (all V1 code has been deleted):

| Feature | Reason for Removal |
|---|---|
| **Global Chat / Alex WebSocket (`/chat/ws`)** | Chat is a lazy UX for complex specs. Smart Forms replace it entirely. |
| **9-State Kanban Board** | Delete `triage`, `backlog`, `queued`, `planning`, `input_needed`, `partial`. Replaced by 3 states. |
| **`input_needed` Deadlocks** | Agents no longer pause execution indefinitely. They assume and proceed. |
| **Per-Agent Git/MCP Bindings** | Over-engineered IT admin work. Git and MCP tools bind at Team or Project level. |
| **Organigramme API** | Vanity UI showing fake corporate hierarchies of AI agents. Pure bloat. |
| **Task Planning WebSocket (`/task-planning/ws`)** | No longer needed — execution is a black box. |
| **Agent Backstories** | CrewAI roleplay baggage. PMs care about output format and system prompts, not backstories. |

---

## 9. The New State Machine

V1 had 9 states with complex transition rules. V2 has 3:

```
 ┌───────────┐       ┌───────────┐       ┌───────────┐
 │  DRAFTING │──────▶│ IN REVIEW │──────▶│  APPROVED │
 │           │       │           │       │           │
 │ AI is     │       │ Human is  │       │ Done.     │
 │ working   │       │ reviewing │       │ Delivered.│
 └───────────┘       └─────┬─────┘       └───────────┘
                           │
                           │ (User requests iteration)
                           │
                           ▼
                     Back to DRAFTING
                     (targeted rewrite)
```

- **Drafting:** The backend is executing the DAG. The user sees a loading/progress state.
- **In Review:** Execution complete. The artifact is ready for human review.
- **Approved:** The user accepted the deliverable. Terminal state.

The only loop: `In Review` → `Drafting` (when the user requests a contextual iteration) → `In Review` (new version ready).

---

## 10. Revised Data Model

The core entity shifts from the **Task** to the **Artifact**.

```
Workspace (user's account)
 └── Roster (persistent agent pool)
      ├── Agent (persistent, learns over time)
      │    ├── specialization
      │    ├── status (learning | ready | working | reflecting)
      │    ├── readiness_score (0-100)
      │    ├── progression_level (apprenti | opérationnel | expert)
      │    ├── model_tier (sonnet | opus)
      │    ├── tools[] (web_search, web_browser, file_read, etc.)
      │    ├── workspace (isolated file system)
      │    │    ├── skills/ (learned preferences & capabilities)
      │    │    ├── work_learnings/ (reflections from past tasks)
      │    │    └── output/ (execution artifacts)
      │    ├── learning_profile
      │    │    ├── completed_artifacts
      │    │    ├── avg_quality_score
      │    │    ├── last_reflection_at
      │    │    └── knowledge_recommendations[]
      │    └── project_history[]
      │
 └── Project (container for related work)
      └── Artifact (the core entity)
           ├── ArtifactVersion (v1, v2, v3...)
           │    ├── file_pointer (S3 path)
           │    ├── token_cost
           │    ├── assumptions[]
           │    ├── sources[]
           │    └── diff_from_previous
           ├── ContextualComment
           │    ├── artifact_version_id
           │    ├── text_highlight_range (start, end)
           │    ├── comment_text
           │    └── triggers next iteration
           └── ExecutionWave (invisible backend worker)
                ├── dag_plan
                ├── assembled_team (auto-selected from roster)
                ├── agent_assignments
                ├── wave_cost
                └── status
```

### Key Entities

| Entity | Description |
|---|---|
| **Roster** | The user's persistent pool of specialized agents. Created during onboarding, customizable over time. |
| **Agent** | Persistent AI entity with a role, specialization, isolated workspace, and accumulated skills/learning. Lives in the roster across projects. Has a status (`learning` → `ready` → `working` → `reflecting`), a `readiness_score` (0-100), a `progression_level` (`apprenti`/`opérationnel`/`expert`), skills, and work learnings. |
| **Project** | Container for related work (e.g., "Q3 Launch"). Has a published context/brief. |
| **Artifact** | The core entity. A deliverable file (markdown, code, etc.). Status: `Drafting` → `In Review` → `Approved`. |
| **ArtifactVersion** | Immutable snapshot. Stores the S3 file pointer, token cost, agent assumptions/sources, and the computed diff from the previous version. Never overwritten. |
| **ContextualComment** | Replaces global task comments. Tied to a specific `ArtifactVersion` and a specific `text_highlight_range`. Triggers the next iteration cycle. |
| **ExecutionWave** | The invisible backend worker that produces an `ArtifactVersion`. Contains the DAG plan, the auto-assembled team (selected from the roster), and cost tracking. |

---

## 11. Backend Architecture Redesign

### A. State Management — PostgreSQL + pgvector

- All V1 `data/*.json` file persistence has been removed.
- **Why:** JSON files corrupt under concurrent execution waves. V2 uses PostgreSQL for ACID-compliant relational data and `pgvector` extension for agent memory/RAG.

### B. Durable Execution — Temporal.io (or Celery/Redis)

- V2 uses Celery + Redis for durable execution instead of bare `asyncio.gather`.
- **Why:** If the FastAPI server restarts, `asyncio` drops all running tasks silently. Celery guarantees durable task execution with a reaper cron to handle crashes.

### C. Stateless Workspaces — S3 / Object Storage

- V2 uses S3-compatible object storage (MinIO) instead of local disk writes.
- **Why:** Local disks prevent horizontal scaling. All artifacts, deliverable versions, and agent context files are stored in object storage.

### D. The Diff Engine & Versioning

- **Implement** strict versioning: `POST /api/artifacts/{id}/iterate` must NEVER overwrite `v1`. It generates `v2` and returns the delta (additions/deletions).
- **Why:** The entire review UX depends on showing the user exactly what changed between versions. Without this, the iteration loop is useless.

### E. Hard Cost Circuit Breakers

- **Implement** `max_budget_usd` on every Artifact and every ExecutionWave.
- **Why:** Without a human babysitting execution, the backend must strictly enforce token limits. If an agent gets stuck in a hallucination loop, the circuit breaker kills the wave before it drains the API balance.

### F. Cascade Resolution Engine

- **Implement** automatic dependency resolution when artifacts are cancelled or fail.
- **Why:** Prevents the execution queue from silently choking on unresolvable dependency chains.

### G. Orphan Detection & Recovery

- **Implement** a background reaper that detects artifacts stuck in `Drafting` with no active execution process.
- **Why:** Server restarts and crashes must not leave artifacts in permanent limbo.

---

## 12. Revised API Surface (High-Level)

The API shifts focus from "Tasks" to "Artifacts and Deliverables."

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/artifacts` | Create a new artifact from a Smart Brief form |
| `GET` | `/api/artifacts/{id}` | Get artifact with current version |
| `GET` | `/api/artifacts/{id}/versions` | List all versions of an artifact |
| `GET` | `/api/artifacts/{id}/versions/{v}/diff` | Get the diff between version `v` and `v-1` |
| `POST` | `/api/artifacts/{id}/iterate` | Trigger a contextual iteration (with `highlighted_text` or `section_id` + comment) |
| `PATCH` | `/api/artifacts/{id}/approve` | Move artifact from `In Review` to `Approved` |
| `POST` | `/api/artifacts/{id}/push` | Push approved code artifact to GitHub |
| `POST` | `/api/briefs/sufficiency-check` | Real-time sufficiency check for the Smart Form (< 2s response) |
| `GET` | `/api/projects/{id}/artifacts` | List all artifacts in a project |
| `POST` | `/api/artifacts/bulk-approve` | Bulk approve multiple artifacts |

### Agency & Roster Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/onboarding` | First-time setup: describe company/domain, generate default roster |
| `GET` | `/api/roster` | List all agents in the user's persistent roster |
| `GET` | `/api/roster/{agent_id}` | Get agent details, specialization, skills, project history |
| `PATCH` | `/api/roster/{agent_id}` | Update agent specialization or configuration |
| `POST` | `/api/roster` | Add a new agent to the roster |
| `DELETE` | `/api/roster/{agent_id}` | Archive an agent (preserves learned skills) |
| `GET` | `/api/roster/{agent_id}/skills` | View accumulated skills and learnings for an agent |

### Agent Learning & Knowledge Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/roster/{agent_id}/learning-profile` | Get learning profile (readiness score, progression level, quality stats) |
| `GET` | `/api/roster/{agent_id}/knowledge-readiness` | Detailed knowledge readiness audit with gap analysis |
| `GET` | `/api/roster/{agent_id}/knowledge-recommendations` | System-suggested actions to fill knowledge gaps |
| `POST` | `/api/roster/{agent_id}/knowledge-recommendations/{rec_id}/apply` | Apply a recommendation (triggers web research in background) |
| `POST` | `/api/roster/{agent_id}/knowledge-recommendations/{rec_id}/dismiss` | Dismiss a recommendation |
| `POST` | `/api/roster/{agent_id}/research` | Trigger autonomous web research on a specific topic |
| `POST` | `/api/roster/{agent_id}/knowledge` | Upload a document or URL to an agent's knowledge base |
| `POST` | `/api/roster/{agent_id}/reflect` | Manually trigger a reflection cycle |
| `PATCH` | `/api/roster/{agent_id}/model` | Change agent model tier (sonnet/opus) |
| `GET` | `/api/roster/readiness/global` | Global knowledge readiness summary across all agents |

### Project Context & Documents Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects/{id}/context` | Get project brief state (draft + published) |
| `PUT` | `/api/projects/{id}/context/draft` | Save a draft project brief |
| `POST` | `/api/projects/{id}/context/publish` | Publish brief and trigger rebriefing of all agents |
| `GET` | `/api/documents` | List all uploaded documents |
| `POST` | `/api/documents` | Upload a document (PDF, DOCX, TXT, MD, CSV, JSON, YAML — max 20MB) |
| `DELETE` | `/api/documents/{doc_id}` | Delete a document |

### Tool Connections (Project/Team Level)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/mcp/connections` | List all MCP connections |
| `POST` | `/api/mcp/connections` | Create an MCP connection (Notion, Slack, custom APIs) |
| `POST` | `/api/mcp/connections/{id}/test` | Test an MCP connection |
| `POST` | `/api/mcp/connections/{id}/discover-tools` | Discover available tools on a connection |
| `DELETE` | `/api/mcp/connections/{id}` | Delete an MCP connection |
| `GET` | `/api/git-providers/connections` | List all Git provider connections |
| `POST` | `/api/git-providers/connections` | Create a Git provider connection (GitHub/GitLab) |
| `POST` | `/api/git-providers/connections/{id}/test` | Test a Git connection |
| `DELETE` | `/api/git-providers/connections/{id}` | Delete a Git connection |

### Usage & Cost Tracking

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/usage` | Get usage stats (tokens, cost by model, daily breakdown) |

### Removed Endpoints

- `ws://*/api/chat/ws` — Global chat WebSocket
- `ws://*/api/task-planning/ws` — Task planning WebSocket
- `GET /api/teams/organigramme` — Org chart endpoint
- All manual task status transition endpoints (`PATCH /api/tasks/{id}/status`)
- `POST /api/tasks/{id}/provide-input` — Input needed resolution

---

## 13. The Smart Brief — Sufficiency Check Deep Dive

The sufficiency check is our most critical UX feature. It is the gatekeeper that ensures agents receive unambiguous specs.

### The Pre-flight Model

The sufficiency check is NOT a real-time keystroke debounce. Calling the LLM on every edit would burn tokens, create race conditions, and add latency to the typing experience. Instead, we use a **pre-flight model**:

1. **User writes their brief** freely in the form — no API calls during editing.
2. **User clicks "Validate" or "Delegate"** — this triggers a single call to `POST /api/briefs/sufficiency-check`.
3. **Backend** runs a fast LLM call (sub-3 second target) that analyzes the complete brief for:
   - Missing constraints (audience, market, timeline, budget)
   - Ambiguous language ("some", "various", "good")
   - Scope creep indicators
   - Missing success criteria
4. **If the brief fails:** The response returns specific issues with text-matching coordinates. The UI displays them inline (highlighted problem areas + actionable suggestions). Submission is **blocked**.
5. **User fixes the issues** and clicks "Validate" again. Repeat until green.
6. **If the brief passes:** Execution begins immediately.

**Cost advantage:** One LLM call per validation click, not hundreds per typing session. A typical brief takes 1-3 validation rounds = 1-3 API calls total.

### Response Schema (Draft)

```json
{
  "eligible": false,
  "score": 62,
  "issues": [
    {
      "severity": "critical",
      "text_range": { "start": 0, "end": 38 },
      "matched_text": "Write a competitive analysis of SaaS.",
      "suggestion": "Which specific competitors? US or EU market? What dimensions (Pricing, UX, Features)?"
    },
    {
      "severity": "warning",
      "text_range": { "start": 40, "end": 72 },
      "matched_text": "Make it comprehensive and detailed.",
      "suggestion": "Define 'comprehensive': How many pages? What sections? What data sources?"
    }
  ]
}
```

Only `critical` issues block submission. `warning` issues are displayed but don't prevent delegation.

---

## 14. Auto-Resolution — No More Deadlocks

In V1, when an agent hit an ambiguity, it paused the entire execution pipeline and waited indefinitely for human input. This is the single worst architectural decision in V1.

### V2 Behavior

1. **Agents never pause.** If they encounter ambiguity during execution, they:
   - Choose the safest default assumption
   - Log the assumption visibly in the deliverable: `[ASSUMPTION: Targeting US market only. Override in review.]`
   - Continue execution
2. **The user sees all assumptions** in the Review phase sidebar.
3. **The user can override** any assumption by highlighting it and requesting a contextual iteration with the correct information.

This keeps the execution pipeline permanently unblocked and shifts the user's role from "blocker" to "optional course-corrector."

---

## 15. Persistent Agent Intelligence

Unlike Claude or ChatGPT which are stateless between conversations, our agents accumulate institutional knowledge:

### Agent Workspaces

Each agent has an isolated workspace containing:
- **Skills:** Markdown files representing learned capabilities and preferences (e.g., "PM hates corporate jargon — use direct, conversational tone")
- **Work Learnings:** Reflections from completed tasks that improve future performance
- **Briefing Context:** Project-specific knowledge injected before each execution

### High-Token Memory Budget

Agent memory (skills + work learnings) is allowed to grow significantly larger than typical system prompts — **5,000 to 8,000 tokens** of accumulated institutional knowledge. This is a deliberate architectural choice:

- **Why large?** This is our moat. The deeper an agent's memory, the better its output quality, the harder it is for users to switch to a competitor. A Content Writer with 6,000 tokens of learned brand voice, tone corrections, and domain knowledge produces output that no fresh Claude prompt can match.
- **Compaction, not truncation:** When memory approaches the ceiling, the reflection system compacts it — merging redundant learnings, removing obsolete preferences, distilling patterns. We never silently truncate.

### Prompt Architecture — The Recency Bias Rule

There is one strict architectural rule for how agent context is assembled into the LLM prompt:

```
┌─────────────────────────────────────────┐
│  LLM Prompt Structure                   │
│                                         │
│  1. System instructions (role, tools)   │
│  2. Agent Skills (5,000-8,000 tokens)   │  ← Long-term memory
│  3. Agent Work Learnings                │  ← Past reflections
│  4. DAG context (upstream agent outputs)│  ← Current execution
│  5. ──────────────────────────────────  │
│  6. CURRENT PROJECT BRIEF               │  ← ALWAYS LAST
│  7. Current task/artifact instructions  │  ← ALWAYS LAST
└─────────────────────────────────────────┘
```

**The rule:** The Current Project Brief and the specific artifact instructions are **always injected at the very end** of the prompt. This leverages LLM recency bias — the model naturally weights the most recent tokens more heavily. This ensures the agent prioritizes the current task's specific requirements over past habits and generic learned patterns.

Without this rule, an agent with 7,000 tokens of past learnings might default to old patterns even when the current brief explicitly asks for something different.

### How Learning Works

1. After each artifact is approved, the agent runs a **reflection step**: what went well, what the user corrected, what to remember.
2. These reflections are saved as skill files in the agent's workspace.
3. Next time the agent is assigned to a similar task, its accumulated skills are loaded into context (positioned before the current brief per the recency rule).
4. **Result:** The 10th competitive analysis an agent writes is dramatically better than the 1st, because it has learned the user's preferences, common corrections, and domain knowledge — while still faithfully following the current brief's specific instructions.

---

## 16. Implementation Roadmap

> **Note:** This section is the original high-level vision roadmap. The detailed, ticket-by-ticket implementation plan is in `docs/TDD/06_IMPLEMENTATION_ROADMAP.md` (49 tickets across 12 sprints). Follow that document for actual implementation — this section is retained for strategic context only.

### Sprint 0: Project Scaffold + Docker + Dependencies
### Sprints 1-5: Backend (Database, Core Services, AI Engine, DAG, Orchestration)
### Sprints 6-7: API Routes (Core + Integrations)
### Sprints 8-10: Frontend (Scaffold, Core Flows, Settings & Polish)
### Sprint 11: Integration & QA

---

## 17. Success Metrics

| Metric | Target | Why |
|---|---|---|
| **Brief-to-Deliverable Time** | < 5 min for standard tasks | Proves the Black Box execution is fast |
| **Review-to-Approval Rate** | > 70% approved on v1 | Proves the sufficiency check produces good specs |
| **Average Iterations per Artifact** | < 3 | Proves agents understand the brief correctly |
| **User Time per Artifact** | < 10 min total (write brief + review) | Proves we save time vs. doing it manually |
| **Cost per Artifact** | Predictable, within budget ceiling | Proves circuit breakers work |
| **Zero Deadlocked Artifacts** | 0 stuck in "Drafting" > 30 min | Proves auto-resolution works |

---

## 18. Target Users

### Primary
- **Startup founders** — wearing 10 hats, need content + code produced fast without hiring
- **Product managers** — need specs, competitive analyses, research, AND feature implementations
- **Small agencies** — need to scale output across code and content without scaling headcount

### Secondary
- **Marketing leads** — launch plans, copy, campaign strategies with data-backed research
- **Engineering leads** — feature builds where product/design/QA input improves code quality

### Why These Users (Not Engineering Teams)

Linear owns engineering teams. We own the users who need **cross-functional output** — deliverables where product thinking, design, code, and quality all matter. A pure engineering team already has Cursor. A founder who needs a settings page that's well-designed, well-specced, AND well-coded has nobody.

---

## 19. The Final Pitch

> **You write the brief. We deliver the work. You review the diff.**
>
> Every AI tool today gives you a single agent working alone. We give you a cross-functional team — product, design, engineering, QA — that collaborates on every deliverable. The designer informs the developer. The QA validates against the spec. Code and content, handled identically.
>
> It's the agency that never sleeps, learns from every project, and costs a fraction of a human team.
