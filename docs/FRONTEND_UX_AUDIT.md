# Frontend UX Audit

## Executive Summary
- The product has real depth and a strong operational model, but the information architecture does not make that depth easy to understand quickly.
- The primary navigation is too cryptic for a product this rich: the global rail is icon-only, labels are underspecified, and a major workflow, `Team Builder`, is missing from first-level navigation.
- `Alex`, team building, project brief, shared documents, and agent knowledge are spread across too many competing surfaces, so the product feels like it has multiple centers of gravity.
- The dashboard is not yet a true command center. It shows numbers, but it does not help the operator decide what to do next.
- The `Tasks` flow contradicts the product promise of explicit planning before execution because the quick-create path launches work immediately.
- Task details and agent workspaces are too important to remain trapped inside a modal and a drawer. These are page-level experiences, not transient overlays.
- `Project Context` has a strong foundation, but it has grown into a mega-hub that mixes source-of-truth editing, document management, readiness diagnostics, and organization optimization.
- `Usage & Costs` contains unusually valuable observability, but it still speaks too much in engine terms and not enough in operator terms.
- Visual hierarchy is often flattened by too much repeated chrome: large shells, repeated badges, shadowed cards, and pill actions with similar weight.
- The strongest parts of the product should be preserved: explicit plan review, publish-and-rebrief briefing flow, rich task outputs, detailed agent workspaces, and structured-output observability.

## Critical UX Findings

### 1. Primary navigation is too cryptic for the actual product complexity
**Severity:** Critical

**Where it appears:** `frontend/components/Sidebar.tsx`, `frontend/components/chat/chat-shell.ts`, `frontend/components/chat/ChatWorkspaceSidebar.tsx`

**What the user experiences:** The global navigation depends on a very narrow icon-only sidebar. The user already has to know the product to know where to go. On top of that, `Team Builder` is a real product workspace but does not exist in first-level navigation.

**Why this is harmful:** In a daily operating tool, the user should not need to reconstruct the product map before acting. The current navigation hides the product model. Discoverability is weak, memorability is poor, and some major workflows look secondary when they are not.

**Recommendation:** Move to a primary nav with visible labels or an expandable rail. Reframe the top-level entries around the actual product concepts: `Alex`, `Brief & Documents`, `Teams & Agents`, `Tasks`, and `AI Observability`. Either promote `Team Builder` into first-level navigation or make it an explicit mode inside `Alex`.

**Expected impact:** Faster orientation, better discoverability, and a significant drop in daily cognitive load.

### 2. The mental model for Alex, context, documents, and agent knowledge is fragmented
**Severity:** Critical

**Where it appears:** `frontend/components/chat/ChatPanel.tsx`, `frontend/components/chat/TeamBuilderChat.tsx`, `frontend/components/project-context/ProjectContextHub.tsx`, `frontend/components/project-context/ProjectDocumentLibrary.tsx`, `frontend/components/agents/WorkspacePanel.tsx`

**What the user experiences:** It is unclear where information is supposed to live. The project brief is in `Project Context`, documents are also managed there but can be cited from chat, agent-specific knowledge is managed in the agent drawer, and `Alex` itself exists across two separate experiences with separate local histories.

**Why this is harmful:** The operator loses confidence in what the actual source of truth is. It becomes unclear whether a decision should be written into the brief, told to Alex, uploaded as a shared document, or injected into an agent workspace. This is a structural UX problem, not a cosmetic one.

**Recommendation:** Make the ownership model explicit and visible.
- `Project Context` should be the source of truth for the global brief and shared documents.
- `Agent Workspace` should be the source of truth for agent-specific enrichment.
- `Alex` should consume and orchestrate those sources, not compete with them.
- `Chat` and `Team Builder` should share one shell with a visible mode switch and visible memory scope.

**Expected impact:** Less duplication, higher trust, and much faster product learning.

### 3. The dashboard does not yet behave like a command center
**Severity:** Critical

**Where it appears:** `frontend/app/page.tsx`, `frontend/components/layout/WorkspacePageShell.tsx`

**What the user experiences:** The home page shows metrics and lists, but not enough prioritization. On load, KPI cards can begin at `0` before data arrives. When real data exists, the page still does not clearly answer "what needs my attention right now?"

**Why this is harmful:** A founder opening the tool wants to know immediately what is ready, what is blocked, what requires a decision, and where to go next. Counters alone feel like a generic dashboard, not an operational cockpit.

**Recommendation:** Replace part of the KPI wall with decision-oriented modules:
- `Needs attention now`
- `Blocked or failed tasks`
- `Agents missing context`
- `Latest important observability signal`
- `Recommended next action`
Use real skeleton states during load instead of showing zero values.

**Expected impact:** The home page becomes useful on open and actually supports daily operations.

### 4. The Tasks flow breaks the product promise of explicit planning before execution
**Severity:** Critical

**Where it appears:** `frontend/app/tasks/page.tsx`

**What the user experiences:** Elsewhere, the product emphasizes clarification, review, and explicit confirmation before execution. On the `Tasks` page, the quick-create path creates and immediately executes a task.

**Why this is harmful:** This breaks the product contract. The operator can no longer tell when the system is in proposal mode versus execution mode. That weakens trust in the guardrails.

**Recommendation:** Make `Alex` plus plan review the default path for any new task. Keep direct creation only as an advanced, clearly labeled secondary path such as `Quick execution without plan review`, with clear consequences.

**Expected impact:** Stronger consistency between product promise and actual behavior, and lower risk of accidental execution.

### 5. The most important inspection surfaces are trapped in transient containers
**Severity:** Critical

**Where it appears:** `frontend/components/tasks/TaskCard.tsx`, `frontend/components/layout/WorkspaceInspectorDrawer.tsx`, `frontend/components/agents/WorkspacePanel.tsx`

**What the user experiences:** Task detail opens inside a very tall, information-dense modal containing result, deliverables, execution plan, timeline, risks, sources, and retry actions. Agent inspection lives inside a fixed right-side drawer that contains what is effectively an entire mini-application.

**Why this is harmful:** These are central experiences, not secondary overlays. Treating them as overlays makes them harder to read, harder to revisit, and harder to anchor mentally. The user loses context easily.

**Recommendation:** Convert task detail into a dedicated page with tabs such as `Summary`, `Deliverables`, `Execution`, and `Sources & Risks`. Keep the modal only for a quick preview. Do the same for agent inspection, or at minimum provide a clear full-page mode from the drawer.

**Expected impact:** Better readability, better workflow continuity, and much less perceived clutter.

### 6. Project Context has become an overloaded mega-hub
**Severity:** Critical

**Where it appears:** `frontend/components/project-context/ProjectContextHub.tsx`, `frontend/components/team/ProjectContextPanel.tsx`

**What the user experiences:** One page contains the global brief, publishing, document library, document preview, global readiness, shared gaps, new team recommendations, and organization change recommendations.

**Why this is harmful:** Even when the page behaves correctly, it still feels heavy. It mixes source-of-truth editing with advanced diagnostics and team design. The core job gets buried under secondary surfaces.

**Recommendation:** Split the page into explicit sections or tabs:
- `Brief`
- `Documents`
- `Readiness`
- `Organization`
The published brief should remain the dominant above-the-fold surface. Organization recommendations should be clearly secondary.

**Expected impact:** A calmer page, clearer hierarchy, and a much stronger sense of what is primary versus optional.

## Medium-Friction Findings

### 1. Page headers consume too much space and weaken action hierarchy
**Severity:** Medium

**Where it appears:** `frontend/components/layout/WorkspacePageShell.tsx`, `frontend/app/team/page.tsx`, `frontend/app/tasks/page.tsx`, `frontend/app/usage/page.tsx`, `frontend/components/project-context/ProjectContextHub.tsx`

**What the user experiences:** Most pages begin with a large shell containing two badges, a large title, a fairly long description, and three or four pill buttons with similar visual weight.

**Why this is harmful:** Too much above-the-fold space is spent on static chrome. The primary action is harder to identify quickly.

**Recommendation:** Reduce header height, remove redundant badges, keep one primary action and one or two secondary actions, and move the rest into a `More` menu.

**Expected impact:** Better hierarchy and faster access to the useful content.

### 2. Terminology is mixed, sometimes too technical and sometimes too vague
**Severity:** Medium

**Where it appears:** `frontend/components/Sidebar.tsx`, `frontend/app/usage/page.tsx`, `frontend/components/agents/WorkspacePanel.tsx`, `frontend/components/project-context/ProjectContextHub.tsx`

**What the user experiences:** The product mixes English and French labels, backend-flavored technical language, and labels that undersell the true purpose of a page.

**Why this is harmful:** The product already asks for a high conceptual load. Mixed terminology adds unnecessary translation work for the user.

**Recommendation:** Standardize the product vocabulary around operator language.
- `Dashboard` -> `Operations` or `Control Center`
- `Mon équipe` -> `Teams & Agents`
- `Usage & Coûts` -> `AI Observability`
- `Knowledge readiness` -> `Context Readiness`
- `fallback heuristique` -> `Heuristic fallback`

**Expected impact:** Faster comprehension, stronger consistency, and a more mature product voice.

### 3. Loading, empty, and error states do not follow a shared pattern
**Severity:** Medium

**Where it appears:** `frontend/app/page.tsx`, `frontend/app/team/page.tsx`, `frontend/app/tasks/page.tsx`, `frontend/app/usage/page.tsx`, `frontend/components/agents/WorkspacePanel.tsx`

**What the user experiences:** Some pages use only a spinner, some use a useful empty state, some show metrics at zero during load, and some show an inline error card.

**Why this is harmful:** Perceived quality becomes inconsistent. The product feels polished in some areas and unfinished in others.

**Recommendation:** Define one shared pattern:
- `loading`: skeletons matching the final structure
- `empty`: educational message plus a primary CTA
- `error`: clear message, likely cause, and explicit retry action
- `freshness`: visible last-updated information where relevant

**Expected impact:** Higher trust and a more robust feel across the app.

### 4. Usage and Costs is technically excellent but not operator-first enough
**Severity:** Medium

**Where it appears:** `frontend/app/usage/page.tsx`, `frontend/app/usage/StructuredOutputFailureSummary.tsx`

**What the user experiences:** The page exposes channels, failure types, stop reasons, and structured-output details directly.

**Why this is harmful:** A daily operator first needs to understand "is this serious?", "what should I do?", and "where is this impacting the product?" Right now the page makes the user translate engine details into operating meaning.

**Recommendation:** Split the page into two reading levels:
- `Operator Summary`
- `Technical Diagnostics`
For each issue, show severity, human-readable meaning, and the next suggested action.

**Expected impact:** Lower fatigue, more immediate value, and better use of the observability surface.

### 5. The agent workspace is powerful but too dense for repeat use
**Severity:** Medium

**Where it appears:** `frontend/components/agents/WorkspacePanel.tsx`

**What the user experiences:** Skills, knowledge, recommendations, uploads, URLs, web research, file browsing, file reading, and agent deletion all live in the same panel.

**Why this is harmful:** The panel feels like a toolbox rather than a focused workspace. The user can do many things, but not always quickly.

**Recommendation:** Add stronger prioritization:
- `Overview`
- `Knowledge`
- `Files`
- `Settings`
At the top, show only the main diagnosis and the next recommended action.

**Expected impact:** Reduced fatigue and better task completion speed.

### 6. Responsive resilience is weak once width decreases
**Severity:** Medium

**Where it appears:** `frontend/app/layout.tsx`, `frontend/components/Sidebar.tsx`, `frontend/components/chat/ChatWorkspaceSidebar.tsx`, `frontend/app/team/page.tsx`, `frontend/components/organigramme/OrgChart.tsx`, `frontend/app/usage/page.tsx`

**What the user experiences:** The product keeps a lot of fixed chrome: a `76px` global rail, a `300px` chat sidebar, a `600px` org chart container, and wide metric grids. At narrower widths the layout compresses quickly.

**Why this is harmful:** Even if the primary use case is desktop, this kind of tool still needs to remain readable on narrow laptops and tablets. Right now the layout becomes rigid too early.

**Recommendation:** Add a collapsible nav, switch to single-column layouts earlier, move the org chart into a dedicated responsive view, and simplify page headers on smaller widths.

**Expected impact:** A more resilient product and fewer layouts that feel fragile.

### 7. Teams defaults to visualization over action
**Severity:** Medium

**Where it appears:** `frontend/app/team/page.tsx`, `frontend/components/organigramme/OrgChart.tsx`

**What the user experiences:** The page opens on the org chart by default, even though the daily jobs are usually inspecting agent state, checking readiness, and managing the structure.

**Why this is harmful:** The org chart is impressive, but less operational than the list view. The default experience feels more like a demo than a management console.

**Recommendation:** Make the operational list the default view and keep the org chart as a secondary visual mode.

**Expected impact:** Faster access to the actions that matter most.

## Polish and Quality Improvements
- Make dashboard KPIs clickable and route to filtered views.
- Replace repeated `Refresh` buttons with `Last updated ...` plus passive background refresh where appropriate.
- Add stronger hover and focus states to all clickable cards, including `AgentCard`, `TaskCard`, and document rows.
- Move destructive actions such as `Delete`, `Reset`, and `Delete agent` into overflow menus instead of exposing them so prominently.
- Slightly reduce shadow usage and nested card-on-card styling, especially in `WorkspacePageShell`.
- Standardize date formatting and numeric formatting, especially on the usage page.
- Remove playful empty-state emoji where they weaken the operational tone.
- Shorten long header descriptions when the content already explains the page.
- Convert technical badges into readable labels with tooltips rather than showing raw internals everywhere.
- Increase contrast on low-signal badges and chips, especially status chips on white backgrounds.

## Cross-Page Consistency Issues
- Primary navigation is icon-only, while local navigation is text-heavy and card-based. The detail level changes too sharply from one layer to another.
- Important concepts do not all live at the same surface depth. Some get a page, some get a drawer, and some get a modal, even when their business importance is higher than that.
- Most headers follow the same `badges + large title + long description + pill actions` pattern, even when the page would benefit from a much more compact presentation.
- The language system is inconsistent: English labels, French labels, backend-flavored technical terms, and operator-facing labels are mixed together.
- Destructive actions do not follow one stable pattern. Some are red buttons, some are tiny icons, and some are exposed as ghost actions.
- `loading`, `empty`, and `error` states vary widely from page to page.
- The product still hesitates about where "context" lives: in chat, in the brief, in documents, in agent knowledge, or in recommendations.
- Badges are overused and often decorative rather than hierarchical.
- Some pages feel like expert tools while others feel like startup dashboards. The product voice and interaction model are not fully unified.

## Workflow-Level Recommendations

### Onboarding and first understanding
The first minute should answer three questions: where to start, what is ready, and what is missing. The dashboard should become a guided state rather than a metrics wall.

### Talking to the assistant
Unify `Chat with Alex` and `Team Builder` inside one experience with a visible mode switch, visible memory scope, and a clear reminder of which sources are attached.

### Creating or managing teams
Make team composition an explicit guided flow that ends on `Teams & Agents` with the newly created team highlighted and a clear next step such as `Feed context`.

### Inspecting agents
Clicking an agent anywhere in the app should open the same inspection experience. Offer a short overview mode and a full-page deep mode instead of relying on one overloaded drawer.

### Understanding project context
Make `Project Context` the unquestioned source of truth for the project brief and shared documents. Readiness and recommendations should support that page, not dominate it.

### Interpreting task outputs
Open with a decision-oriented summary first: final result, deliverables, sources, and risks. The detailed execution plan should be available next, not compete immediately for attention.

### Understanding usage and observability
Start with "what should concern you" and "what changed recently", then let the user drill down into channels, repair paths, and failure kinds.

### Acting on knowledge recommendations
Each recommendation should lead directly into the right action with as much prefill as possible: upload a document, add a URL, launch research, then return the user to the same diagnostic context.

## Suggested Redesign Priorities
1. Redesign global navigation and rename sections around the true product model.
2. Unify `Alex`, `Team Builder`, and `Brief & Documents` into one coherent entry system with explicit source-of-truth ownership.
3. Rework the dashboard into a decision-oriented command center instead of a metric wall.
4. Redesign the task lifecycle so planning is the default, task detail becomes a page, and execution detail is secondary to outcome.
5. Split `Project Context` into clear layers: brief, documents, readiness, and organization.
6. Turn agent inspection into a more progressive experience with less density and less exposed destructive action.
7. Reframe `Usage` as operator-first, with technical observability beneath that layer.
8. Run a full responsive pass across all shells and fixed-width containers.

## Quick Wins
- Add visible labels to the global sidebar or introduce an expandable rail.
- Add `Team Builder` to first-level navigation, or make it an explicit mode under `Alex`.
- Replace loading-time zero KPIs with skeletons.
- Make KPI cards and `View all` links route to filtered operational views.
- Rename `Mon équipe` to `Teams & Agents`.
- Rename `Usage & Coûts` to `AI Observability`.
- Rename `New task` to `Quick execution` if it continues to bypass plan review.
- Reduce the number of always-visible header buttons.
- Move secondary and destructive actions into a `More` menu.
- Show `Last updated` on operational pages.
- Keep advanced recommendations collapsed by default wherever they are not the primary job.
- Translate raw technical badges into readable labels with tooltips for the underlying detail.
