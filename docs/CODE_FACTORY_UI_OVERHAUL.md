# Code Factory UI Overhaul Plan

> **Status:** Plan — not yet implemented
> **Goal:** Transform the generic "AI agency for knowledge work" frontend into a purpose-built code factory where every surface is optimized for writing, reviewing, and shipping code.
> **Principle:** Code in, code out. No prose artifacts, no content workflows, no generic "deliverables."

---

## Current State (What's Wrong)

The frontend was built as a generic AI work-delegation UI. Specific problems:

1. **Generic language everywhere** — "Projects", "Deliverables", "Artifacts", "Agency Roster", "Agent Team"
2. **Prose-first form fields** — "Target Audience", "Goal (what success looks like)", placeholder "Q3 Competitive Analysis"
3. **Document/Code type toggle still present** — should be code-only
4. **Project creation asks for nothing code-specific** — no repo URL, no tech stack, no language
5. **Task creation form is a content brief** — not a code specification with acceptance criteria
6. **No task type selector** — can't distinguish feature from bug from refactor
7. **Review UI is prose-focused** — no syntax highlighting, no side-by-side diff, no test results
8. **Sidebar is generic** — "Projects" with a folder icon, "Agency Roster" with a people icon
9. **No visibility into git state** — PR status, branch, commits not surfaced in the main UI
10. **Engineering context page is a plain textarea** — no structured sections for architecture, code standards, testing strategy

---

## Phase 1 — Language & Identity

**Goal:** Every label, placeholder, icon, and description reads like a code tool, not a content tool. Fastest way to shift perception.

### 1.1 Sidebar rebrand
- Brand: "Agent Team" → product name or just the logo icon
- "Projects" (FolderKanban) → "Codebases" (Code2 icon)
- "Agency Roster" (Users) → "Team" (Users icon is fine)
- "Settings" stays
- Add bottom section: small "Active tunnel" or "API status" indicator

### 1.2 Kill prose artifact type
- Remove the Document/Code toggle from `smart-brief-form.tsx` entirely
- Hardcode `artifact_type: "code"` in `CreateArtifactRequest`
- Remove `FileText` icon and "Document" button (lines 206-217 in smart-brief-form)
- Update `ArtifactType` to just `"code"` (remove `"prose"` from type union)

### 1.3 Rename throughout
| Current | New | Where |
|---|---|---|
| "New Project" | "New Codebase" | create-project-dialog |
| "Create a new project to organize your deliverables" | "Create a codebase to organize your code tasks" | create-project-dialog |
| "Q3 Product Launch" (placeholder) | "payment-service" or "frontend-redesign" | create-project-dialog |
| "New Deliverable" | "New Task" | artifacts/new page, project layout tabs |
| "Artifacts" (tab) | "Tasks" | project layout |
| "Project Brief" | "Engineering Context" | project layout tab |
| "Documents" (tab) | "Reference Docs" | project layout tab |
| "Generating your agency" (onboarding) | "Setting up your engineering team" | onboarding-form |
| "Agency Roster" | "Team" | sidebar |

### 1.4 Icon updates
- Project card: `FileText` → `GitBranch` or `Code2`
- Task list items: show type-specific icons (Bug, Wrench, Zap, Shield, etc.)

**Files touched:** `sidebar.tsx`, `create-project-dialog.tsx`, `smart-brief-form.tsx`, `project-card.tsx`, `onboarding-form.tsx`, project layout, artifacts/new page

---

## Phase 2 — Project Creation

**Goal:** When you create a codebase, the system knows what tech you're working with from day one.

### 2.1 Expand create-project-dialog
Add fields after name/description:
- **Repository URL** (optional) — input with "https://github.com/..." placeholder. If provided, link to a git connection.
- **Primary Language** — dropdown: TypeScript, Python, Go, Rust, Java, C#, Ruby, PHP, Swift, Kotlin, Other
- **Framework** (optional) — context-sensitive: if TypeScript → Next.js, React, Express, etc. If Python → FastAPI, Django, Flask, etc.
- **Package Manager** (optional) — npm, pnpm, yarn, pip, cargo, go modules, etc.

### 2.2 Update project card
Replace the current generic card (`name, description, artifact_count, created_at`) with:
- **Repo badge** — `owner/repo` with GitBranch icon (if linked)
- **Language badge** — colored dot + language name (like GitHub)
- **Task counts by status** — "2 in progress, 1 in review, 5 done" instead of just "8 artifacts"
- **Last activity** — "3h ago" relative time instead of absolute created_at
- Drop the generic `FileText` icon

### 2.3 Backend: extend Project model
- Add `primary_language`, `framework`, `package_manager` columns (all optional TEXT)
- Add `git_repo_url` at project level (currently only on artifacts)
- Migration 0011
- Update `CreateProjectRequest` / `ProjectDetail` schemas
- Frontend types updated to match

**Files touched:** `create-project-dialog.tsx`, `project-card.tsx`, project API schemas, Project model, migration, `api.ts`

---

## Phase 3 — Task Creation (The Brief Form)

**Goal:** Replace the prose-oriented brief form with a code specification form that maps directly to DAG templates.

### 3.1 Task type selector (replaces artifact_type toggle)
Top of form — a radio/pill group selecting the kind of code work:

| Type | Maps to Template | Icon |
|---|---|---|
| Feature | `full_feature` / `backend_feature` / `frontend_feature` | Sparkles |
| Bug Fix | `bug_fix` | Bug |
| Refactor | `refactor` | Wrench |
| Security Fix | `security_fix` | Shield |
| Performance | `performance` | Zap |
| Infrastructure | `infra_devops` | Server |
| API Integration | `api_integration` | Plug |
| Architecture | `architecture` | Blocks |

The type determines which fields appear and which DAG template is used. The router still picks the exact template, but the UI pre-filters.

### 3.2 Remap form fields per type

**All types get:**
| Field | Label | Replaces | Placeholder |
|---|---|---|---|
| `title` | "Title" | same | "Add user authentication flow" |
| `description` | "Description" | same | "Implement JWT-based auth with refresh tokens..." |
| `context` | "Technical Context" | "Context" | "FastAPI backend, PostgreSQL, existing User model..." |
| `git_repo_url` | "Repository" | same | (inherited from project, with override) |
| `git_base_branch` | "Base Branch" | same | "main" |

**Feature/Bug/Refactor/Security get:**
| Field | Label | Replaces | Notes |
|---|---|---|---|
| `goal` | "Acceptance Criteria" | "Goal" | Multi-line. "When X, then Y. Given A, expect B." |
| `target_audience` | *removed* | — | Meaningless for code |

**Bug Fix gets additionally:**
| Field | Label | Notes |
|---|---|---|
| (new) `severity` | "Severity" | critical / high / medium / low — UI-only, passed in description to LLM |
| (new) `reproduction_steps` | "Steps to Reproduce" | Textarea, appended to description |

**Infrastructure gets additionally:**
| Field | Label | Notes |
|---|---|---|
| (new) `affected_services` | "Affected Services" | Comma-separated, appended to context |

### 3.3 Auto-inherit from project
- `git_repo_url` pre-filled from project's repo (if set in Phase 2)
- `context` pre-filled with project's language/framework info
- Git connection dropdown pre-selected if project is linked

### 3.4 Template hint
Below the type selector, show a subtle line: "This will use the **Full Product Feature** template with PM Lead + Design Lead planning, 2 parallel workers, and Tech Lead review." Updates dynamically as the user selects a type.

**Files touched:** `smart-brief-form.tsx` (major rewrite), `api.ts` (type updates), sufficiency check prompts (code-specific)

---

## Phase 4 — Engineering Context (replaces Project Brief)

**Goal:** Replace the free-text textarea with a structured engineering context editor.

### 4.1 Structured sections
Replace the single textarea with collapsible sections, each with its own field:

| Section | Label | Placeholder | Purpose |
|---|---|---|---|
| Architecture | "Architecture Overview" | "Monorepo with Nx. Backend: FastAPI + SQLAlchemy. Frontend: Next.js 15 App Router..." | System structure |
| Code Standards | "Code Standards & Conventions" | "Use ruff for linting. Type hints on all public functions. No relative imports..." | Style rules |
| Testing Strategy | "Testing Requirements" | "Unit tests required for all business logic. E2E with Playwright. Min 80% coverage..." | Testing expectations |
| API Contracts | "API Conventions" | "REST with /api/v1 prefix. Snake_case fields. Cursor pagination on all lists..." | API patterns |
| Database | "Database & Schema Notes" | "PostgreSQL 16 + pgvector. Alembic for migrations. TEXT PKs (UUID v4)..." | Schema context |
| Deployment | "Deployment & Infrastructure" | "Docker Compose for dev. GitHub Actions CI. Deploy to AWS ECS..." | Infra context |

### 4.2 Each section is independently saveable
- Auto-save on blur (debounced 2s, same as current brief editor)
- Sections concatenated into `brief_draft` / `brief_published` for the backend (backward compatible)
- Visual indicator: saved / unsaved per section

### 4.3 Publish all at once
- "Publish Context" button (replaces "Publish Brief")
- Publishing distributes context to all agents (same briefing mechanism)

**Files touched:** `brief-editor.tsx` (major rewrite), project brief page

---

## Phase 5 — Task List & Status

**Goal:** The task list should look like a code-aware issue tracker, not a generic artifact grid.

### 5.1 Task list redesign
Replace the current artifact list (title, type, status, version, cost) with:

| Column | Content |
|---|---|
| Type icon | Bug/Feature/Refactor icon based on type |
| Title | Task title (link to detail) |
| Status | Badge: drafting / building / in review / approved (color-coded) |
| Branch | `feature/add-auth` — clickable link to PR if exists |
| PR | #42 — link to GitHub PR (if `git_pr_url` exists) |
| Version | v3 |
| Cost | $0.14 |
| Created | "2h ago" relative |

### 5.2 Status badges
| Status | Label | Color |
|---|---|---|
| `drafting` | "Draft" | gray |
| `drafting` + wave running | "Building..." | blue, animated |
| `in_review` | "In Review" | amber |
| `approved` | "Merged" | green |
| `cancelled` | "Cancelled" | red, muted |

### 5.3 Quick filters
Pill bar at top: All / Building / In Review / Merged / Draft

**Files touched:** project `[projectId]/page.tsx`, new task list component, `api.ts` type adjustments

---

## Phase 6 — Code Review UI

**Goal:** When reviewing a completed task, the UI should feel like a code review tool — not a prose viewer.

### 6.1 File tree sidebar
Left panel showing the file manifest as a tree:
```
src/
  auth/
    middleware.ts
    jwt.ts
  api/
    routes/
      users.ts
tests/
  auth.test.ts
```
Click a file to view it. Highlight files that changed between versions.

### 6.2 Code viewer with syntax highlighting
- Use a lightweight syntax highlighter (Shiki or Prism via `react-syntax-highlighter`)
- Show file content with line numbers
- Language auto-detected from file extension

### 6.3 Diff viewer
- Toggle: "Files" / "Diff" modes
- Side-by-side or unified diff between versions
- Syntax highlighted
- Additions in green, deletions in red (standard diff colors)
- Use the existing `version-switcher.tsx` to pick which versions to compare

### 6.4 Git context panel
Top bar of the review page showing:
- Branch name: `feature/add-auth`
- PR link: `owner/repo#42` (clickable)
- Base branch: `main`
- File count: "7 files, +342 / -28 lines"

### 6.5 Iteration via inline comments
- Click a line number to leave a comment (replaces the text-selection floating toolbar for code)
- Comment includes file path + line number automatically
- Maps to the existing `IterateRequest` with `file_path` and `highlight_start`

**Files touched:** `artifact-review.tsx` (major), new `code-viewer.tsx`, new `code-diff-viewer.tsx`, new `file-tree.tsx`, `version-switcher.tsx` update

---

## Phase 7 — Onboarding for Code

**Goal:** Onboarding should ask the right questions to generate an engineering team, not a generic agency.

### 7.1 Simplify and focus the form

**Keep:**
- Company name
- Tech stack (make it a tag selector, not free text: "Python", "TypeScript", "Go", "React", "FastAPI", "PostgreSQL", etc.)
- Company stage

**Change:**
- "Domain Description" → "What does your product do?" (same field, better label)
- "Use Case" selector → remove. It's always "Code". Hardcode.
- "Team Size" → "Engineering team size" with context: "How many engineers work on this codebase?"

**Add:**
- "Primary Language" — dropdown (same as project creation)
- "Testing Framework" — optional, helps agents write tests in the right framework
- "CI/CD Platform" — optional: GitHub Actions, GitLab CI, Jenkins, CircleCI, None

**Remove:**
- "Target Audience" (meaningless for code factory onboarding)
- "Main Goals" (too vague — replaced by per-project engineering context)

### 7.2 Agent generation messaging
- "Generating your agency..." → "Building your engineering team..."
- Roster preview should show role badges prominently: "Tech Lead", "Backend Developer", "Frontend Developer", "QA Engineer"
- Show which DAG templates each agent can work on

**Files touched:** `onboarding-form.tsx`, `roster-preview.tsx`, onboarding API schemas (backend)

---

## Phase 8 — Team Page

**Goal:** The roster page should feel like an engineering team directory, not a generic agent grid.

### 8.1 Group by role
Two sections:
- **Leads** — planning and review agents (Tech Lead, PM Lead, Design Lead, Security Lead, etc.)
- **Engineers** — execution agents (Backend Dev, Frontend Dev, QA, DevOps, etc.)

### 8.2 Agent card redesign
| Current | New |
|---|---|
| Generic name + specialization | Name + role badge (Lead/Worker) + specialization |
| Readiness score as number | Readiness bar (visual, color-coded) |
| Status text | Status dot (green=ready, blue=working, amber=learning, purple=reflecting) |
| "Completed artifacts" | "Tasks completed" with count |

### 8.3 Agent detail: skills as code knowledge
- Skills section: show skills with code-related icons (database, API, frontend, testing, security)
- Work learnings: show which templates/task types the agent has experience with
- History: list of completed tasks with PR links

**Files touched:** `roster/page.tsx`, `agent-card.tsx`, `agent-detail-tabs.tsx`

---

## Phase 9 — Settings Code Focus

**Goal:** Settings pages should prioritize git connections and workspace configuration.

### 9.1 Reorder settings tabs
Current: Workspace / Git / MCP / Usage
New: **Git** / Workspace / MCP / Usage

Git is the most important integration for a code factory — it should be first.

### 9.2 Git settings improvements
- Show connected repos with webhook status (green dot if active)
- "Test Connection" shows remaining API rate limit
- Webhook URL shows the current tunnel/production URL prominently
- Quick link to generate a PAT with the right scopes

### 9.3 Workspace settings → Engineering Defaults
- Rename "Workspace" tab to "Defaults"
- Show: default language, default framework, default test framework, default CI/CD
- These become the pre-filled values for new project creation

**Files touched:** settings layout, settings pages, workspace settings page

---

## Dependency Graph

```
Phase 1 (Language) ──────────────┐
                                 │
Phase 2 (Project Creation) ──────┤
                                 │ (all UI changes, can parallelize)
Phase 3 (Task Creation) ─────────┤
                                 │
Phase 4 (Engineering Context) ───┤
                                 │
Phase 5 (Task List) ─────────────┤
                                 ▼
                          Phase 6 (Code Review UI)
                                 │  ← heaviest phase, needs syntax
                                 │    highlighting and diff libraries
                                 ▼
Phase 7 (Onboarding) ─── can run in parallel with anything
Phase 8 (Team Page) ──── can run in parallel with anything
Phase 9 (Settings) ───── can run in parallel with anything
```

**Phase 1 should go first** — it's the fastest way to shift the entire product feel. Phases 2-5 can run in any order. Phase 6 is the heaviest and has a dependency on a syntax highlighting library. Phases 7-9 are independent polish.

---

## Backend Changes Required

Most phases are frontend-only. Backend changes needed:

| Phase | Backend Change |
|---|---|
| 2 | Add `primary_language`, `framework`, `package_manager`, `git_repo_url` to Project model + migration 0011 |
| 3 | No backend change — task type is UI-only, maps to template via router |
| 4 | No backend change — sections concatenated into existing `brief_draft` field |
| 7 | Hardcode `use_case: "code"` in onboarding, update schemas |

---

## New Dependencies

| Phase | Package | Purpose |
|---|---|---|
| 6 | `shiki` or `react-syntax-highlighter` | Syntax highlighting in code viewer |
| 6 | `diff` or `jsdiff` | Computing diffs between file versions |

---

## Out of Scope (Future)

These would be valuable but are too large for this overhaul:

- Full code browser (browsing repo files beyond artifacts)
- Terminal/build output viewer
- CI/CD pipeline status dashboard
- Code coverage metrics integration
- Dependency vulnerability alerts
- Merge conflict resolution UI
- Multi-repo monorepo support
