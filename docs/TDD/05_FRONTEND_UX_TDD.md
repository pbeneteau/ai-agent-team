# Phase 5 — Frontend Architecture & UX/UI (TDD)

> **Document type:** Technical Design Document
> **Status:** Draft
> **Source of truth:** `docs/VISION_2.0.md`, `docs/TDD/01_PRD_AND_WORKFLOWS.md`, `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md`, `docs/TDD/03_AI_AGENT_ENGINE_TDD.md`, `docs/TDD/04_API_AND_INTEGRATIONS_TDD.md`
> **Scope:** Next.js application structure, design system, state management, component hierarchy, real-time communication, and UX patterns. No backend logic (see TDD-02/03), no API specs (see TDD-04).

---

## Architectural Decisions Log

| ID | Decision | Rationale |
|---|---|---|
| **AD-18** | Zustand for UI state, TanStack Query for server state | Clean separation: TanStack Query handles caching, refetching, optimistic updates, and stale-while-revalidate for all API data. Zustand handles ephemeral UI state (modals, sidebar, selection). No prop drilling, no Context overhead. |
| **AD-19** | Fresh design system (not inheriting V1 "Ops Desk" tokens) | V1's design system was built around a conversational UI with ops-canvas/ops-surface/ops-ink token namespacing. V2's Artifact-First model has fundamentally different UI primitives (diff viewers, brief forms, roster grids). Starting fresh avoids shoehorning. |
| **AD-20** | WebSocket for push notifications + polling for heartbeat | WebSocket delivers event-driven notifications (artifact complete, agent status changes) without polling overhead. Heartbeat uses 3-second polling because the data changes continuously during execution and the polling endpoint (`GET /api/artifacts/{id}/status`) is cheap. Combining both avoids WebSocket message flooding during execution. |
| **AD-21** | Native browser text selection + floating toolbar for contextual comments | Native `Selection` API is reliable across browsers and requires zero custom text rendering. A floating toolbar (like Medium/Notion) appears on text selection, avoiding permanent UI clutter. Character offsets are computed from the selection range against the rendered content. |
| **AD-22** | Toggle between unified and side-by-side diff modes | Users have strong preferences. Unified diffs are better for prose (reading flow). Side-by-side diffs are better for structured content (tables, lists). A toggle lets users choose. `react-diff-viewer-continued` supports both modes natively. |
| **AD-23** | Both light and dark mode from day one | CSS custom properties make this near-zero incremental cost when done from the start. Retrofitting dark mode later requires auditing every color value — far more expensive. shadcn/ui has built-in dark mode support. |

---

## 1. Tech Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Framework** | Next.js | 15+ | App Router, SSR, file-based routing, server components |
| **Language** | TypeScript | 5.x | Type safety across the entire frontend |
| **Styling** | Tailwind CSS | v4 | Utility-first CSS, CSS-first configuration |
| **Component Library** | shadcn/ui | latest | Accessible, composable primitives (built on Radix UI) |
| **Server State** | TanStack Query | v5 | API data fetching, caching, refetching, optimistic updates |
| **UI State** | Zustand | v5 | Lightweight stores for ephemeral UI state |
| **Diff Viewer** | react-diff-viewer-continued | latest | Unified + side-by-side diffs for prose artifact review |
| **Markdown Rendering** | react-markdown + remark-gfm | latest | Rendering artifact prose content with GFM support |
| **Form Handling** | React Hook Form + Zod | latest | Brief form validation, controlled inputs, schema validation |
| **Icons** | Lucide React | latest | Consistent icon set, tree-shakeable |
| **Date Formatting** | date-fns | latest | Lightweight date utilities (no Moment.js) |

### Build & Dev Tooling

| Tool | Purpose |
|---|---|
| **pnpm** | Package manager (fast, disk-efficient) |
| **ESLint** | Linting (Next.js + TypeScript presets) |
| **Prettier** | Code formatting |

### Runtime Requirements

- Node.js 20+
- Backend API at `http://localhost:8000/api` (proxied via Next.js rewrites in development)

---

## 2. Design System

### 2.1 Philosophy

The design system is built around three principles:

1. **Content-first density.** The UI exists to present artifact content, not to decorate. Generous whitespace around content blocks. Minimal chrome.
2. **Review ergonomics.** Diff viewers, comment toolbars, and version navigation must not compete with the content for attention. Subdued controls, prominent content.
3. **Professional restraint.** No gradients, no animations beyond functional transitions (< 200ms), no decorative elements. The product handles serious work — the UI should feel like a tool, not a toy.

### 2.2 Color Tokens (CSS Custom Properties)

All colors are defined as CSS custom properties on `:root` (light) and `.dark` (dark), using oklch for perceptual uniformity.

```css
/* tokens.css */
:root {
  /* Neutral scale — used for backgrounds, borders, text */
  --color-bg-primary:      oklch(0.99 0 0);       /* Page background */
  --color-bg-secondary:    oklch(0.97 0 0);       /* Card/panel background */
  --color-bg-tertiary:     oklch(0.94 0 0);       /* Hover states, subtle fills */
  --color-bg-inverse:      oklch(0.15 0 0);       /* Inverted backgrounds (tooltips) */

  --color-border-primary:  oklch(0.90 0 0);       /* Default borders */
  --color-border-secondary: oklch(0.85 0 0);      /* Emphasized borders */

  --color-text-primary:    oklch(0.15 0 0);       /* Body text */
  --color-text-secondary:  oklch(0.45 0 0);       /* Muted/secondary text */
  --color-text-tertiary:   oklch(0.60 0 0);       /* Placeholders, disabled */
  --color-text-inverse:    oklch(0.99 0 0);       /* Text on inverse backgrounds */

  /* Semantic colors */
  --color-accent:          oklch(0.55 0.15 250);  /* Primary action (buttons, links) */
  --color-accent-hover:    oklch(0.48 0.15 250);  /* Hover state */
  --color-accent-subtle:   oklch(0.95 0.03 250);  /* Accent background tint */

  --color-success:         oklch(0.55 0.15 155);  /* Approved, complete, added */
  --color-success-subtle:  oklch(0.95 0.04 155);  /* Success background */
  --color-warning:         oklch(0.70 0.15 80);   /* Warnings, advisory issues */
  --color-warning-subtle:  oklch(0.95 0.04 80);   /* Warning background */
  --color-danger:          oklch(0.55 0.18 25);   /* Errors, critical issues, removed */
  --color-danger-subtle:   oklch(0.95 0.04 25);   /* Error background */

  /* Diff-specific */
  --color-diff-added-bg:   oklch(0.95 0.05 145);  /* Green highlight for additions */
  --color-diff-added-text: oklch(0.30 0.10 145);  /* Dark green text */
  --color-diff-removed-bg: oklch(0.95 0.05 25);   /* Red highlight for removals */
  --color-diff-removed-text: oklch(0.30 0.10 25); /* Dark red text */

  /* Surfaces & elevation */
  --shadow-sm:   0 1px 2px oklch(0 0 0 / 0.05);
  --shadow-md:   0 2px 8px oklch(0 0 0 / 0.08);
  --shadow-lg:   0 4px 16px oklch(0 0 0 / 0.12);

  --radius-sm:   6px;
  --radius-md:   8px;
  --radius-lg:   12px;
}

.dark {
  --color-bg-primary:      oklch(0.13 0 0);
  --color-bg-secondary:    oklch(0.17 0 0);
  --color-bg-tertiary:     oklch(0.21 0 0);
  --color-bg-inverse:      oklch(0.92 0 0);

  --color-border-primary:  oklch(0.25 0 0);
  --color-border-secondary: oklch(0.32 0 0);

  --color-text-primary:    oklch(0.92 0 0);
  --color-text-secondary:  oklch(0.65 0 0);
  --color-text-tertiary:   oklch(0.50 0 0);
  --color-text-inverse:    oklch(0.13 0 0);

  --color-accent:          oklch(0.65 0.15 250);
  --color-accent-hover:    oklch(0.72 0.15 250);
  --color-accent-subtle:   oklch(0.20 0.04 250);

  --color-success:         oklch(0.65 0.15 155);
  --color-success-subtle:  oklch(0.20 0.04 155);
  --color-warning:         oklch(0.75 0.12 80);
  --color-warning-subtle:  oklch(0.20 0.04 80);
  --color-danger:          oklch(0.65 0.15 25);
  --color-danger-subtle:   oklch(0.20 0.04 25);

  --color-diff-added-bg:   oklch(0.20 0.04 145);
  --color-diff-added-text: oklch(0.75 0.10 145);
  --color-diff-removed-bg: oklch(0.20 0.04 25);
  --color-diff-removed-text: oklch(0.75 0.10 25);

  --shadow-sm:   0 1px 2px oklch(0 0 0 / 0.20);
  --shadow-md:   0 2px 8px oklch(0 0 0 / 0.30);
  --shadow-lg:   0 4px 16px oklch(0 0 0 / 0.40);
}
```

### 2.3 Typography

| Token | Value | Usage |
|---|---|---|
| `--font-sans` | `"Inter", system-ui, sans-serif` | All UI text |
| `--font-mono` | `"JetBrains Mono", ui-monospace, monospace` | Code, diffs, technical content |
| `--text-xs` | `0.75rem / 1rem` | Badges, captions |
| `--text-sm` | `0.875rem / 1.25rem` | Secondary text, table cells |
| `--text-base` | `1rem / 1.5rem` | Body text, form inputs |
| `--text-lg` | `1.125rem / 1.75rem` | Section headings |
| `--text-xl` | `1.25rem / 1.75rem` | Page titles |
| `--text-2xl` | `1.5rem / 2rem` | Hero/feature headings |

### 2.4 Spacing Scale

Tailwind v4 default: `0.25rem` (1) increments. Key breakpoints used:

| Token | Value | Typical Usage |
|---|---|---|
| `spacing-1` | `0.25rem` | Icon gaps |
| `spacing-2` | `0.5rem` | Compact padding (badges, pills) |
| `spacing-3` | `0.75rem` | Button padding, list gaps |
| `spacing-4` | `1rem` | Card padding, section gaps |
| `spacing-6` | `1.5rem` | Section padding |
| `spacing-8` | `2rem` | Page section margins |
| `spacing-12` | `3rem` | Major section breaks |

### 2.5 Dark Mode Implementation

Dark mode is controlled via a `class` strategy on `<html>`:

```typescript
// lib/theme.ts
type Theme = "light" | "dark" | "system";

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "system";
  return (localStorage.getItem("theme") as Theme) ?? "system";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  root.classList.toggle("dark", isDark);
  localStorage.setItem("theme", theme);
}
```

The Zustand UI store exposes `theme` and `setTheme`. The `ThemeProvider` component (rendered in the root layout) applies the theme on mount and listens for `prefers-color-scheme` changes when in `system` mode.

---

## 3. Application Shell & Routing

### 3.1 App Router Structure

```
app/
├── layout.tsx                    # Root layout: providers, sidebar, theme
├── page.tsx                      # Redirect → /projects (or /onboarding if first visit)
│
├── onboarding/
│   └── page.tsx                  # J1: First-time onboarding flow
│
├── projects/
│   ├── layout.tsx                # Projects shell: sidebar nav context
│   ├── page.tsx                  # Project list (dashboard)
│   │
│   └── [projectId]/
│       ├── layout.tsx            # Project-scoped layout: project name, tabs
│       ├── page.tsx              # Artifact list for this project
│       ├── brief/
│       │   └── page.tsx          # Project brief editor (draft/publish)
│       ├── documents/
│       │   └── page.tsx          # Project document management
│       └── artifacts/
│           ├── new/
│           │   └── page.tsx      # J2/J3: Smart Brief form (new deliverable)
│           └── [artifactId]/
│               ├── page.tsx      # Artifact detail (heartbeat OR review)
│               └── versions/
│                   └── [version]/
│                       └── page.tsx  # Specific version view + diff
│
├── roster/
│   ├── page.tsx                  # J4: Agency Roster overview grid
│   └── [agentId]/
│       └── page.tsx              # Agent detail (profile, skills, history)
│
├── settings/
│   ├── page.tsx                  # Settings shell → redirect to first tab
│   ├── git/
│   │   └── page.tsx              # J6: Git provider connections
│   ├── mcp/
│   │   └── page.tsx              # J6: MCP connections
│   └── usage/
│       └── page.tsx              # J6: Usage & cost tracking + budget
│
└── api/
    └── [...proxy]/               # Optional: API proxy for development (rewrites to backend)
```

### 3.2 Root Layout

```tsx
// app/layout.tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <QueryClientProvider>
            <WebSocketProvider>
              <div className="flex h-screen">
                <Sidebar />
                <main className="flex-1 overflow-y-auto">
                  {children}
                </main>
              </div>
              <NotificationToast />
            </WebSocketProvider>
          </QueryClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
```

### 3.3 Sidebar Navigation

Persistent left sidebar (collapsible). Items:

| Icon | Label | Route | Badge |
|---|---|---|---|
| FolderKanban | **Projects** | `/projects` | — |
| Users | **Agency Roster** | `/roster` | Agent count |
| Settings | **Settings** | `/settings` | — |

The sidebar also displays:
- **Global Readiness Indicator:** A small status dot showing overall roster readiness (data from `GET /api/roster/readiness/global`). Green = all agents ready, Yellow = some learning, Red = attention needed.
- **Active Executions:** If any artifacts are in `drafting` status, show a subtle pulse indicator with count.

---

## 4. State Management

### 4.1 TanStack Query — Server State

All backend data flows through TanStack Query. This gives us:
- **Automatic caching** (stale-while-revalidate)
- **Background refetching** (on window focus, on interval)
- **Optimistic updates** (for mutations like approve, cancel)
- **Query invalidation** (WebSocket events trigger targeted invalidation)

#### Query Key Convention

```typescript
// lib/query-keys.ts
export const queryKeys = {
  // Roster
  roster: {
    all:    () => ["roster"] as const,
    list:   (filters?: RosterFilters) => ["roster", "list", filters] as const,
    detail: (id: string) => ["roster", id] as const,
    skills: (id: string, category?: string) => ["roster", id, "skills", category] as const,
    learningProfile: (id: string) => ["roster", id, "learning-profile"] as const,
    recommendations: (id: string) => ["roster", id, "recommendations"] as const,
    globalReadiness: () => ["roster", "readiness", "global"] as const,
  },

  // Projects
  projects: {
    all:    () => ["projects"] as const,
    list:   (cursor?: string) => ["projects", "list", cursor] as const,
    detail: (id: string) => ["projects", id] as const,
    context: (id: string) => ["projects", id, "context"] as const,
    documents: (id: string) => ["projects", id, "documents"] as const,
  },

  // Artifacts
  artifacts: {
    all:      () => ["artifacts"] as const,
    list:     (projectId: string, filters?: ArtifactFilters) => ["artifacts", "list", projectId, filters] as const,
    detail:   (id: string) => ["artifacts", id] as const,
    status:   (id: string) => ["artifacts", id, "status"] as const,
    versions: (id: string) => ["artifacts", id, "versions"] as const,
    file:     (id: string, version: number, path: string) => ["artifacts", id, "versions", version, "files", path] as const,
  },

  // Integrations
  gitProviders: {
    all:   () => ["git-providers"] as const,
    list:  () => ["git-providers", "list"] as const,
    repos: (connectionId: string) => ["git-providers", connectionId, "repos"] as const,
  },
  mcp: {
    all:  () => ["mcp"] as const,
    list: () => ["mcp", "list"] as const,
  },

  // Usage
  usage: {
    all:   () => ["usage"] as const,
    stats: (period?: string) => ["usage", "stats", period] as const,
  },
} as const;
```

#### Polling Configuration

```typescript
// Heartbeat polling: only when artifact is in "drafting" status
const { data: status } = useQuery({
  queryKey: queryKeys.artifacts.status(artifactId),
  queryFn: () => api.artifacts.getStatus(artifactId),
  refetchInterval: (query) =>
    query.state.data?.status === "drafting" ? 3_000 : false,
  enabled: !!artifactId,
});
```

#### Stale Times

| Data Type | Stale Time | Rationale |
|---|---|---|
| Roster list | 30s | Agents change status infrequently; WebSocket handles urgent updates |
| Agent detail | 30s | Same as above |
| Project list | 60s | Rarely changes during a session |
| Artifact list | 10s | May change during active work |
| Artifact status | 0s (always fresh) | Heartbeat polling needs latest data |
| Artifact versions | 60s | Versions are immutable once created |
| File content | Infinity | Files within a version never change (immutable) |
| Usage stats | 120s | Aggregated data, no urgency |
| Global readiness | 30s | WebSocket handles real-time agent status changes |

### 4.2 Zustand — UI State

Zustand stores manage client-only, ephemeral state that does not belong in the URL or in TanStack Query.

#### `useUIStore`

```typescript
// stores/ui-store.ts
interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // Theme
  theme: "light" | "dark" | "system";
  setTheme: (theme: "light" | "dark" | "system") => void;

  // Diff viewer
  diffMode: "unified" | "side-by-side";
  setDiffMode: (mode: "unified" | "side-by-side") => void;

  // Modals
  activeModal: string | null;
  modalProps: Record<string, unknown>;
  openModal: (id: string, props?: Record<string, unknown>) => void;
  closeModal: () => void;
}
```

Persisted to `localStorage`: `sidebarCollapsed`, `theme`, `diffMode`.

#### `useSelectionStore`

```typescript
// stores/selection-store.ts
interface SelectionState {
  // Text selection for contextual commenting
  selectedText: string | null;
  selectionRange: { start: number; end: number } | null;
  selectionRect: DOMRect | null;  // Position for floating toolbar
  filePath: string | null;

  setSelection: (text: string, range: { start: number; end: number }, rect: DOMRect, filePath: string | null) => void;
  clearSelection: () => void;
}
```

Not persisted. Cleared on navigation.

### 4.3 URL State

Some state lives in the URL for shareability and back/forward navigation:

| State | URL Location | Example |
|---|---|---|
| Current project | Path segment | `/projects/abc-123` |
| Current artifact | Path segment | `/projects/abc-123/artifacts/def-456` |
| Version being viewed | Path segment | `.../versions/2` |
| Artifact list filters | Query params | `?status=in_review` |
| Roster list filters | Query params | `?status=ready` |

---

## 5. API Client

### 5.1 Base Client

```typescript
// lib/api-client.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new ApiError(res.status, error?.error?.code ?? "UNKNOWN", error?.error?.message ?? res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}
```

### 5.2 API Module Organization

```typescript
// lib/api/index.ts
export const api = {
  onboarding: { create: (data) => request("/onboarding", { method: "POST", body: JSON.stringify(data) }) },

  roster: {
    list:           (params?) => request(`/roster?${qs(params)}`),
    get:            (id) => request(`/roster/${id}`),
    create:         (data) => request("/roster", { method: "POST", body: JSON.stringify(data) }),
    update:         (id, data) => request(`/roster/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    archive:        (id) => request(`/roster/${id}`, { method: "DELETE" }),
    deletePermanent: (id) => request(`/roster/${id}/permanent`, { method: "DELETE" }),
    getSkills:      (id, category?) => request(`/roster/${id}/skills?${qs({ category })}`),
    getLearningProfile: (id) => request(`/roster/${id}/learning-profile`),
    triggerResearch: (id, topic) => request(`/roster/${id}/research`, { method: "POST", body: JSON.stringify({ topic }) }),
    triggerReflection: (id) => request(`/roster/${id}/reflect`, { method: "POST" }),
    uploadKnowledge: (id, formData) => request(`/roster/${id}/knowledge`, { method: "POST", body: formData, headers: {} }),
    getRecommendations: (id) => request(`/roster/${id}/knowledge-recommendations`),
    applyRecommendation: (id, recId) => request(`/roster/${id}/knowledge-recommendations/${recId}/apply`, { method: "POST" }),
    dismissRecommendation: (id, recId) => request(`/roster/${id}/knowledge-recommendations/${recId}/dismiss`, { method: "POST" }),
    globalReadiness: () => request("/roster/readiness/global"),
  },

  projects: {
    list:      (params?) => request(`/projects?${qs(params)}`),
    get:       (id) => request(`/projects/${id}`),
    create:    (data) => request("/projects", { method: "POST", body: JSON.stringify(data) }),
    update:    (id, data) => request(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete:    (id) => request(`/projects/${id}`, { method: "DELETE", headers: { "X-Confirm-Delete": "true" } }),
    getContext: (id) => request(`/projects/${id}/context`),
    saveDraft: (id, content) => request(`/projects/${id}/context/draft`, { method: "PUT", body: JSON.stringify({ content }) }),
    publish:   (id) => request(`/projects/${id}/context/publish`, { method: "POST" }),
    listDocuments: (id) => request(`/projects/${id}/documents`),
    uploadDocument: (id, formData) => request(`/projects/${id}/documents`, { method: "POST", body: formData, headers: {} }),
    deleteDocument: (id, docId) => request(`/projects/${id}/documents/${docId}`, { method: "DELETE" }),
  },

  artifacts: {
    create:     (data) => request("/artifacts", { method: "POST", body: JSON.stringify(data) }),
    get:        (id) => request(`/artifacts/${id}`),
    getStatus:  (id) => request(`/artifacts/${id}/status`),
    validate:   (id) => request(`/artifacts/${id}/validate`, { method: "POST" }),
    delegate:   (id, data?) => request(`/artifacts/${id}/delegate`, { method: "POST", body: JSON.stringify(data ?? {}) }),
    getVersions: (id) => request(`/artifacts/${id}/versions`),
    getFile:    (id, version, path) => fetch(`${API_BASE}/artifacts/${id}/versions/${version}/files/${path}`).then(r => r.text()),
    iterate:    (id, data) => request(`/artifacts/${id}/iterate`, { method: "POST", body: JSON.stringify(data) }),
    approve:    (id) => request(`/artifacts/${id}/approve`, { method: "PATCH" }),
    cancel:     (id) => request(`/artifacts/${id}/cancel`, { method: "PATCH" }),
    listByProject: (projectId, params?) => request(`/projects/${projectId}/artifacts?${qs(params)}`),
  },

  briefs: {
    sufficiencyCheck: (data) => request("/briefs/sufficiency-check", { method: "POST", body: JSON.stringify(data) }),
  },

  gitProviders: {
    list:       () => request("/git-providers/connections"),
    create:     (data) => request("/git-providers/connections", { method: "POST", body: JSON.stringify(data) }),
    test:       (id) => request(`/git-providers/connections/${id}/test`, { method: "POST" }),
    listRepos:  (id) => request(`/git-providers/connections/${id}/repos`),
    configureWebhook: (id, owner, repo) => request(`/git-providers/connections/${id}/repos/${owner}/${repo}/webhook`, { method: "POST" }),
    delete:     (id) => request(`/git-providers/connections/${id}`, { method: "DELETE" }),
  },

  mcp: {
    list:          () => request("/mcp/connections"),
    create:        (data) => request("/mcp/connections", { method: "POST", body: JSON.stringify(data) }),
    test:          (id) => request(`/mcp/connections/${id}/test`, { method: "POST" }),
    discoverTools: (id) => request(`/mcp/connections/${id}/discover-tools`, { method: "POST" }),
    delete:        (id) => request(`/mcp/connections/${id}`, { method: "DELETE" }),
  },

  usage: {
    getStats:     (period?) => request(`/usage?${qs({ period })}`),
    updateBudget: (amount) => request("/usage/budget", { method: "PATCH", body: JSON.stringify({ monthly_budget_usd: amount }) }),
  },

  health: {
    check: () => request("/health"),
  },
} as const;
```

---

## 6. WebSocket & Notifications

### 6.1 WebSocket Connection

A single WebSocket connection per session, managed by a React context provider at the root layout level.

```typescript
// lib/websocket.ts
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

interface WSEvent {
  type: string;
  payload: Record<string, unknown>;
}
```

**Connection lifecycle:**
1. Connect on app mount (after initial render).
2. Reconnect on disconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s).
3. Heartbeat ping every 30 seconds to detect stale connections.
4. Disconnect on window unload.

### 6.2 Event Types

| Event Type | Payload | Frontend Action |
|---|---|---|
| `artifact.status_changed` | `{ artifact_id, status, project_id }` | Invalidate `artifacts.detail`, `artifacts.list`, `artifacts.status`. Show toast if `status == "in_review"`. |
| `agent.status_changed` | `{ agent_id, status, readiness_score }` | Invalidate `roster.detail`, `roster.list`, `roster.globalReadiness`. |
| `execution.wave_completed` | `{ artifact_id, wave_number, total_waves }` | Invalidate `artifacts.status` (triggers fresh heartbeat data). |
| `execution.failed` | `{ artifact_id, error_message }` | Invalidate `artifacts.detail`, `artifacts.status`. Show error toast. |
| `budget.warning` | `{ usage_pct, remaining_usd }` | Show persistent warning banner if `usage_pct >= 90`. |

### 6.3 WebSocket → Query Invalidation Bridge

```typescript
// providers/websocket-provider.tsx
function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();

  useEffect(() => {
    const ws = createWebSocket();

    ws.onMessage((event: WSEvent) => {
      switch (event.type) {
        case "artifact.status_changed":
          queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.detail(event.payload.artifact_id) });
          queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.status(event.payload.artifact_id) });
          queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.list(event.payload.project_id) });

          if (event.payload.status === "in_review") {
            showToast({ title: "Deliverable Ready for Review", variant: "success" });
          }
          break;

        case "agent.status_changed":
          queryClient.invalidateQueries({ queryKey: queryKeys.roster.detail(event.payload.agent_id) });
          queryClient.invalidateQueries({ queryKey: queryKeys.roster.all() });
          break;

        case "execution.failed":
          queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.detail(event.payload.artifact_id) });
          showToast({ title: "Execution Failed", description: event.payload.error_message, variant: "error" });
          break;

        case "budget.warning":
          showToast({ title: "Budget Warning", description: `${event.payload.usage_pct}% used`, variant: "warning", persistent: true });
          break;
      }
    });

    return () => ws.close();
  }, [queryClient]);

  return <>{children}</>;
}
```

### 6.4 Toast Notifications

Toasts are rendered by a `<NotificationToast />` component in the root layout (using shadcn/ui's `Sonner` integration). Variants:

| Variant | Duration | Use |
|---|---|---|
| `success` | 5s auto-dismiss | Artifact ready, agent ready |
| `error` | Persistent (manual dismiss) | Execution failed, push failed |
| `warning` | Persistent | Budget warning, agent not ready |
| `info` | 4s auto-dismiss | General informational |

---

## 7. Component Architecture

### 7.1 Shared Components

Located in `components/`:

```
components/
├── ui/                          # shadcn/ui primitives (auto-generated)
│   ├── button.tsx
│   ├── card.tsx
│   ├── dialog.tsx
│   ├── dropdown-menu.tsx
│   ├── input.tsx
│   ├── textarea.tsx
│   ├── badge.tsx
│   ├── tabs.tsx
│   ├── tooltip.tsx
│   ├── skeleton.tsx
│   ├── separator.tsx
│   ├── progress.tsx
│   ├── sonner.tsx               # Toast notifications
│   └── ...
│
├── layout/
│   ├── sidebar.tsx              # App sidebar navigation
│   ├── page-header.tsx          # Reusable page header (title + actions)
│   └── empty-state.tsx          # Empty state illustration + CTA
│
├── shared/
│   ├── status-badge.tsx         # Artifact/agent status pill (Drafting, In Review, etc.)
│   ├── cost-display.tsx         # Formatted USD display with token breakdown
│   ├── cursor-pagination.tsx    # "Load more" / infinite scroll pagination
│   ├── confirm-dialog.tsx       # Confirmation modal for destructive actions
│   ├── file-upload.tsx          # Drag-and-drop file upload zone
│   └── readiness-indicator.tsx  # Agent readiness score bar (0-100)
```

### 7.2 Feature Components

Organized by feature domain, co-located with their routes:

```
features/
├── onboarding/
│   ├── onboarding-form.tsx          # Company context form
│   ├── roster-preview.tsx           # Generated roster preview with edit
│   └── agent-card-editable.tsx      # Inline-editable agent card
│
├── projects/
│   ├── project-list.tsx             # Project grid/list
│   ├── project-card.tsx             # Individual project card
│   ├── project-create-dialog.tsx    # New project modal
│   ├── project-brief-editor.tsx     # Rich text editor for project brief
│   └── document-manager.tsx         # Document upload/list/delete
│
├── artifacts/
│   ├── smart-brief-form.tsx         # The Smart Brief creation form (Section 8)
│   ├── sufficiency-feedback.tsx     # Inline validation issue display
│   ├── delegate-preview.tsx         # Team + plan preview before confirming
│   ├── heartbeat-panel.tsx          # Execution progress UI (Section 9)
│   ├── artifact-review.tsx          # Review shell: content + sidebar (Section 10)
│   ├── prose-viewer.tsx             # Rendered markdown content
│   ├── prose-diff-viewer.tsx        # Diff between versions (Section 11)
│   ├── code-artifact-review.tsx     # Code artifact: PR link + metadata
│   ├── version-switcher.tsx         # Version dropdown/tabs (v1, v2, v3...)
│   ├── review-sidebar.tsx           # Sources, assumptions, cost
│   └── artifact-actions.tsx         # Approve, Cancel, Iterate buttons
│
├── comments/
│   ├── floating-comment-toolbar.tsx # Appears on text selection (Section 12)
│   ├── comment-form.tsx             # Inline comment input
│   └── comment-thread.tsx           # List of contextual comments on a version
│
├── roster/
│   ├── roster-grid.tsx              # Agent grid with filters
│   ├── agent-card.tsx               # Agent summary card
│   ├── agent-detail.tsx             # Full agent profile
│   ├── agent-skills-list.tsx        # Skill entries with token budget
│   ├── agent-history.tsx            # Completed artifacts table
│   ├── knowledge-recommendations.tsx # Gap analysis + apply/dismiss
│   └── research-dialog.tsx          # Manual research trigger form
│
├── settings/
│   ├── git-connections.tsx          # Git provider CRUD
│   ├── git-repo-list.tsx            # Repo listing with webhook status
│   ├── mcp-connections.tsx          # MCP connection CRUD
│   ├── mcp-tools-list.tsx           # Discovered tools display
│   ├── usage-dashboard.tsx          # Cost charts and breakdowns
│   └── budget-editor.tsx            # Monthly budget ceiling control
│
└── notifications/
    ├── notification-toast.tsx       # Global toast container
    └── websocket-provider.tsx       # WS connection + query invalidation
```

---

## 8. Smart Brief Form

The primary input surface for creating deliverables. Maps to **Journey J2/J3** from TDD-01.

### 8.1 Form Fields

| Field | Input Type | Validation | Required |
|---|---|---|---|
| **Title** | Text input | Max 200 chars | Yes |
| **Artifact Type** | Toggle: `Document` / `Code` | — | Yes |
| **Goal** | Textarea | Max 500 chars | No |
| **Target Audience** | Text input | Max 200 chars | No |
| **Context** | Textarea (expandable) | Max 2000 chars | No |
| **Description** | Textarea (large, expandable) | Max 5000 chars | Yes |
| **Max Budget** | Number input | Min $0.50, default $5.00 | No |
| *Code-only fields:* | | | |
| **Target Repository** | Dropdown (from Git connections) | Must have active connection | Yes (code) |
| **Base Branch** | Dropdown (from repo branches) | Default: repo default branch | No |

### 8.2 Form Schema (Zod)

```typescript
const briefSchema = z.object({
  project_id: z.string().uuid(),
  artifact_type: z.enum(["prose", "code"]),
  title: z.string().min(1).max(200),
  goal: z.string().max(500).optional(),
  target_audience: z.string().max(200).optional(),
  context: z.string().max(2000).optional(),
  description: z.string().min(10).max(5000),
  max_budget_usd: z.number().min(0.5).default(5.0),
  git_repo_url: z.string().url().optional(),
  git_base_branch: z.string().optional(),
}).refine(
  (data) => data.artifact_type !== "code" || !!data.git_repo_url,
  { message: "Target repository is required for code artifacts", path: ["git_repo_url"] }
);
```

### 8.3 Sufficiency Check Integration

**Flow:**
1. User fills in the form.
2. User clicks **"Validate"** (or **"Delegate"**, which validates first).
3. Frontend calls `POST /api/artifacts/{id}/validate`.
4. If `eligible: false`, the `<SufficiencyFeedback>` component renders issues inline:
   - Each issue is positioned next to its `field` (title, goal, context, description).
   - The `matched_text` is highlighted within the field using string search and a `<mark>` tag.
   - `critical` issues show a red indicator. `warning` issues show a yellow indicator.
   - A summary banner at the top: "2 issues found — 1 critical (blocks submission)."
5. User edits the brief. Clicks **"Validate"** again.
6. If `eligible: true`, green checkmark. **"Delegate"** button becomes active.

### 8.4 Delegation Flow

**Flow:**
1. User clicks **"Delegate to Team"**.
2. Frontend calls `POST /api/artifacts/{id}/delegate` with `{ confirm: false }` (preview mode).
3. `<DelegatePreview>` modal shows:
   - **Selected template** name and description.
   - **Wave plan** — ordered list of waves, each showing agent names and roles.
   - **Estimated cost** (e.g., "~$0.65").
   - **Override controls** — user can swap agents in each slot (dropdown of roster agents).
4. User clicks **"Confirm & Start"**.
5. Frontend calls `POST /api/artifacts/{id}/delegate` with `{ confirm: true }`.
6. On `202 Accepted`, navigate to the artifact detail page (which now shows the heartbeat UI).

---

## 9. Heartbeat UI

Displayed on the artifact detail page when `status === "drafting"`. Maps to VISION_2.0 Section 4, Phase 2.

### 9.1 Data Source

Polling `GET /api/artifacts/{id}/status` every 3 seconds via TanStack Query (see Section 4.1).

Response shape:
```json
{
  "status": "drafting",
  "execution": {
    "wave_id": "uuid",
    "current_step": 2,
    "total_steps": 3,
    "step_labels": ["Researching competitors", "Drafting analysis", "QA & compilation"],
    "cost_usd": 0.42,
    "started_at": "2026-03-26T10:30:00Z",
    "estimated_remaining_seconds": 120
  }
}
```

### 9.2 Visual Design

```
┌─────────────────────────────────────────────────────┐
│  Q3 Competitive Analysis                            │
│  Drafting...                                        │
│                                                     │
│  ✅ Step 1/3: Researching competitors               │
│  ⏳ Step 2/3: Drafting analysis                      │
│  ○  Step 3/3: QA & compilation                      │
│                                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░  67%         │
│                                                     │
│  Cost: $0.42  •  Est. remaining: ~2 min             │
│                                                     │
│  ┌───────────────────────────────────────┐          │
│  │          [Cancel Execution]           │          │
│  └───────────────────────────────────────┘          │
└─────────────────────────────────────────────────────┘
```

### 9.3 Component Behavior

- **Step indicators:** Three states — `complete` (checkmark, green), `active` (spinner, accent), `pending` (circle outline, muted).
- **Progress bar:** `current_step / total_steps` as a percentage. Animated fill (CSS transition, 300ms).
- **Cost counter:** Updates on every poll. Formatted as `$X.XX`.
- **Time estimate:** `estimated_remaining_seconds` converted to human-readable. Shows "Finishing up..." when < 10s.
- **Cancel button:** Calls `PATCH /api/artifacts/{id}/cancel`. Requires confirmation dialog: "Are you sure? Execution will be stopped. Any completed work is preserved."
- **Transition:** When the poll returns `status !== "drafting"`, the component fades out and the artifact detail page switches to the review UI. TanStack Query invalidation ensures the artifact detail and versions are fresh.

---

## 10. Artifact Review UI

Displayed when `status === "in_review"`. The primary review surface for prose artifacts. Maps to TDD-01 Journey J2 Steps 10-14 and Journey J3 Steps 10-13.

### 10.1 Prose Review Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  Version: [v1 ▾] [v2] [v3]     │  [Diff: v1 → v2]  [View PR]      │
├──────────────────────────────────┬───────────────────────────────────┤
│                                  │                                   │
│  ┌────────────────────────────┐  │  REVIEW SIDEBAR                  │
│  │                            │  │                                   │
│  │  Rendered Markdown         │  │  ▸ Sources (3)                   │
│  │  Content                   │  │    • competitor-pricing.com       │
│  │                            │  │    • gartner-report-2025.pdf      │
│  │  (selectable text —        │  │    • g2-reviews-notion.html       │
│  │   floating toolbar         │  │                                   │
│  │   appears on selection)    │  │  ▸ Assumptions (2)               │
│  │                            │  │    • US market only               │
│  │                            │  │    • Current pricing (not hist.)  │
│  │                            │  │                                   │
│  │                            │  │  ▸ Cost                          │
│  │                            │  │    $0.42 (3,200 in / 1,800 out)  │
│  │                            │  │                                   │
│  │                            │  │  ▸ Comments (1)                  │
│  │                            │  │    "Add per-seat breakdown" — v1  │
│  │                            │  │                                   │
│  └────────────────────────────┘  │  ┌─────────────────────────────┐ │
│                                  │  │  [✓ Approve] [✕ Cancel]     │ │
│                                  │  └─────────────────────────────┘ │
└──────────────────────────────────┴───────────────────────────────────┘
```

### 10.2 Component Breakdown

| Component | Responsibility |
|---|---|
| `<ArtifactReview>` | Shell: fetches artifact, versions, files. Routes to prose or code review. |
| `<VersionSwitcher>` | Tabs or dropdown for navigating between versions. Shows version count and which is selected. |
| `<ProseViewer>` | Renders the selected version's markdown content via `react-markdown` + `remark-gfm`. Handles text selection events (see Section 12). |
| `<ProseDiffViewer>` | Diff between two versions (see Section 11). Shown when user toggles diff mode or navigates to diff route. |
| `<ReviewSidebar>` | Collapsible right panel showing sources, assumptions, cost, and comments for the current version. Data from `GET /api/artifacts/{id}/versions`. |
| `<ArtifactActions>` | Bottom bar with **Approve** (prose) and **Cancel** buttons. Approve triggers `PATCH /api/artifacts/{id}/approve` with optimistic update. |

### 10.3 Code Artifact Review

Code artifacts do NOT use the in-app diff viewer. The review page shows:

```
┌──────────────────────────────────────────────────┐
│  API Authentication Endpoint                     │
│  Status: In Review  •  v1  •  $0.85              │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  🔗 View Pull Request on GitHub            │  │
│  │     acme/webapp #42                        │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ▸ Files changed (4)                             │
│    • src/routes/auth.ts                          │
│    • src/middleware/jwt.ts                        │
│    • tests/auth.test.ts                          │
│    • README.md                                   │
│                                                  │
│  ▸ Sources (2)                                   │
│  ▸ Assumptions (1)                               │
│  ▸ Cost: $0.85                                   │
│                                                  │
│  ┌──────────────────────────────────────┐        │
│  │  Feedback (optional — or use GitHub) │        │
│  │  [                                 ] │        │
│  │  [Submit Feedback & Iterate]         │        │
│  └──────────────────────────────────────┘        │
│                                                  │
│  Note: This artifact will be automatically       │
│  approved when the PR is merged on GitHub.       │
│  [✕ Cancel]                                      │
└──────────────────────────────────────────────────┘
```

**Key differences from prose review:**
- No in-app diff viewer. PR link is the primary CTA.
- File list is displayed (from `file_manifest`) but files are not rendered in-app.
- An optional text feedback form allows in-app iteration (calls `POST /api/artifacts/{id}/iterate` without highlight range).
- No **Approve** button — approval is via PR merge (detected by webhook). A note explains this.
- **Cancel** button is still available.

---

## 11. Diff Viewer (Prose Artifacts)

### 11.1 Library

`react-diff-viewer-continued` — a maintained fork of `react-diff-viewer`. Supports:
- Unified diff mode (single column, inline additions/deletions)
- Side-by-side diff mode (two columns)
- Syntax highlighting
- Custom styling

### 11.2 Data Flow

Diffs are computed **on the frontend** (AD-6 from TDD-02). The flow:

1. User selects two versions to compare (default: current version vs. previous version).
2. Frontend fetches both version's files via `GET /api/artifacts/{id}/versions/{v}/files/{path}`.
3. File content (strings) are passed to `react-diff-viewer-continued`.
4. The diff is computed and rendered client-side.

For multi-file artifacts, the diff viewer shows a file-by-file diff with a file selector.

### 11.3 Mode Toggle

The diff mode toggle (`unified` / `side-by-side`) is stored in the Zustand `UIStore` and persisted to `localStorage`. The toggle control is rendered in the diff viewer toolbar.

```typescript
// features/artifacts/prose-diff-viewer.tsx
function ProseDiffViewer({ oldContent, newContent, oldVersion, newVersion }: Props) {
  const { diffMode, setDiffMode } = useUIStore();

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-[var(--color-text-secondary)]">
          Comparing v{oldVersion} → v{newVersion}
        </span>
        <ToggleGroup value={diffMode} onValueChange={setDiffMode}>
          <ToggleGroupItem value="unified">Unified</ToggleGroupItem>
          <ToggleGroupItem value="side-by-side">Side by Side</ToggleGroupItem>
        </ToggleGroup>
      </div>

      <ReactDiffViewer
        oldValue={oldContent}
        newValue={newContent}
        splitView={diffMode === "side-by-side"}
        useDarkTheme={/* read from theme */}
        styles={diffStyles}
      />
    </div>
  );
}
```

### 11.4 Custom Diff Styles

The diff viewer's default theme is overridden to use our design tokens:

```typescript
const diffStyles = {
  variables: {
    light: {
      diffViewerBackground: "var(--color-bg-primary)",
      addedBackground: "var(--color-diff-added-bg)",
      addedColor: "var(--color-diff-added-text)",
      removedBackground: "var(--color-diff-removed-bg)",
      removedColor: "var(--color-diff-removed-text)",
      wordAddedBackground: "var(--color-success-subtle)",
      wordRemovedBackground: "var(--color-danger-subtle)",
      gutterBackground: "var(--color-bg-secondary)",
      gutterColor: "var(--color-text-tertiary)",
      codeFoldBackground: "var(--color-bg-tertiary)",
    },
    dark: {
      diffViewerBackground: "var(--color-bg-primary)",
      addedBackground: "var(--color-diff-added-bg)",
      addedColor: "var(--color-diff-added-text)",
      removedBackground: "var(--color-diff-removed-bg)",
      removedColor: "var(--color-diff-removed-text)",
      wordAddedBackground: "var(--color-success-subtle)",
      wordRemovedBackground: "var(--color-danger-subtle)",
      gutterBackground: "var(--color-bg-secondary)",
      gutterColor: "var(--color-text-tertiary)",
      codeFoldBackground: "var(--color-bg-tertiary)",
    },
  },
};
```

Because our CSS variables already switch between light and dark, the diff viewer inherits the correct colors automatically.

---

## 12. Contextual Commenting System

The mechanism for users to provide targeted feedback on prose artifacts. Maps to TDD-01 Journey J2 Steps 12-13 and TDD-04 `POST /api/artifacts/{id}/iterate`.

### 12.1 Selection Detection

Uses the native browser `Selection` API. A `useTextSelection` hook monitors `mouseup` and `keyup` events within the prose viewer container.

```typescript
// hooks/use-text-selection.ts
function useTextSelection(containerRef: RefObject<HTMLElement>) {
  const setSelection = useSelectionStore((s) => s.setSelection);
  const clearSelection = useSelectionStore((s) => s.clearSelection);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    function handleSelectionChange() {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) {
        clearSelection();
        return;
      }

      const range = selection.getRangeAt(0);

      // Ensure selection is within our container
      if (!container.contains(range.commonAncestorContainer)) {
        clearSelection();
        return;
      }

      const text = selection.toString().trim();
      if (text.length < 3) {
        clearSelection();
        return;
      }

      // Compute character offsets relative to the container's text content
      const preRange = document.createRange();
      preRange.selectNodeContents(container);
      preRange.setEnd(range.startContainer, range.startOffset);
      const start = preRange.toString().length;
      const end = start + text.length;

      // Get selection position for floating toolbar
      const rect = range.getBoundingClientRect();

      setSelection(text, { start, end }, rect, null);
    }

    document.addEventListener("selectionchange", handleSelectionChange);
    return () => document.removeEventListener("selectionchange", handleSelectionChange);
  }, [containerRef, setSelection, clearSelection]);
}
```

### 12.2 Floating Comment Toolbar

A small floating UI that appears above the selected text, containing a "Comment" button.

```
                    ┌─────────────────┐
                    │  💬 Comment     │
                    └────────┬────────┘
                             ▼
            "The pricing comparison shows Notion..."
             ════════════════════════════════════
```

**Positioning:** Absolutely positioned based on `selectionRect` from the Zustand store. Centered horizontally above the selection, with collision detection (flips below if near the top of the viewport).

**Behavior:**
1. Appears when `selectedText` is non-null and length >= 3 characters.
2. Clicking "Comment" opens an inline comment form below the toolbar.
3. User types their instruction (e.g., "Add per-seat pricing breakdown").
4. Clicking "Submit" calls `POST /api/artifacts/{id}/iterate` with:
   - `highlighted_text`: the selected text
   - `highlight_start`: character offset start
   - `highlight_end`: character offset end
   - `instruction`: the user's comment
5. On success (`202 Accepted`), the selection is cleared, a toast confirms "Iteration started," and the artifact transitions to the heartbeat view (status → `drafting`).
6. Clicking outside the toolbar or pressing Escape clears the selection.

### 12.3 Comment Thread

The `<ReviewSidebar>` includes a **Comments** section listing all `contextual_comments` for the current version. Each comment shows:
- The highlighted text (truncated to 60 chars with ellipsis)
- The user's instruction
- The resulting version (if iteration completed)
- Timestamp

Comments are read-only in MVP — no editing, no threading. They serve as an audit trail of iteration requests.

---

## 13. Onboarding Flow

A standalone flow for first-time users. Maps to TDD-01 Journey J1.

### 13.1 Multi-Step Form

The onboarding page (`/onboarding`) is a multi-step wizard:

| Step | Component | Fields |
|---|---|---|
| 1 | `<OnboardingForm>` | Company Name, Domain/Industry, Tech Stack (optional), Team Size, Primary Use Case (content/code/both) |
| 2 | `<RosterPreview>` | Generated roster grid — each agent card is inline-editable (name, specialization). Add/remove buttons. |
| 3 | Confirmation | Summary + "Confirm Roster" CTA |

**Step 1 → Step 2:** Calls `POST /api/onboarding` with the company context. The response contains the generated roster.

**Step 2 → Step 3:** Local state only — edits are tracked in React Hook Form state. On "Confirm Roster," any agent edits are sent as `PATCH /api/roster/{id}` calls.

**After confirmation:** Redirect to `/projects` (dashboard). The sidebar shows agents in `learning` status with progress indicators.

### 13.2 Guard

The root page (`/`) checks if onboarding is complete by calling `GET /api/roster/readiness/global`. If the response returns a `404` or `total_agents === 0`, redirect to `/onboarding`. Otherwise, redirect to `/projects`.

---

## 14. Roster Management UI

Maps to TDD-01 Journey J4.

### 14.1 Roster Grid

The roster overview (`/roster`) displays all agents in a responsive grid (3 columns on desktop, 2 on tablet, 1 on mobile).

**Agent Card contents:**
- Agent name (bold)
- Specialization (one line, truncated)
- Status badge: `learning` (blue, pulse animation), `ready` (green), `working` (amber), `reflecting` (purple)
- Progression level badge: `apprenti`, `opérationnel`, `expert`
- Knowledge readiness bar (0-100, colored: red < 40, yellow 40-70, green > 70)
- Completed artifacts count

**Filters:** Status filter pills at the top (All / Learning / Ready / Working / Reflecting).

**Actions:** "Add Agent" button opens `<ResearchDialog>` for creating a new agent.

### 14.2 Agent Detail Page

The agent detail page (`/roster/[agentId]`) uses tabs:

| Tab | Content | Data Source |
|---|---|---|
| **Profile** | Name, specialization, description (all editable). Model tier toggle (Sonnet/Opus). Status + progression badges. | `GET /api/roster/{id}` |
| **Skills** | List of skill entries with title, token count, source artifact. Category filter (skill / work_learning / briefing). Token budget indicator (used/max). | `GET /api/roster/{id}/skills` |
| **History** | Table of completed artifacts: title, date, version count. Links to artifact detail. | Derived from artifact list (filtered by agent participation — requires backend support or client-side join). |
| **Knowledge** | Readiness score breakdown (4 factors from TDD-03 Section 10). Knowledge recommendations with Apply/Dismiss. Manual "Research a Topic" form. Upload knowledge (file/URL). | `GET /api/roster/{id}/learning-profile`, `GET /api/roster/{id}/knowledge-recommendations` |

**Destructive actions** (bottom of profile tab):
- **Archive Agent:** `DELETE /api/roster/{id}`. Confirmation dialog.
- **Delete Permanently:** `DELETE /api/roster/{id}/permanent`. Danger zone confirmation with agent name typed to confirm.

---

## 15. Project & Brief Management

### 15.1 Project Dashboard

The project list page (`/projects`) shows a grid of project cards:
- Project name
- Description (2 lines, truncated)
- Artifact count
- Brief status badge: `none` (gray), `draft` (yellow), `published` (green)
- Creation date

"New Project" button opens a dialog with name + description fields.

### 15.2 Project Detail

The project detail page (`/projects/[projectId]`) has a tabbed layout:

| Tab | Content |
|---|---|
| **Artifacts** | List of artifacts in this project with status filters. "New Deliverable" CTA. Each row: title, type (prose/code), status badge, version count, cost, date. |
| **Brief** | Project brief editor. Draft auto-saves (debounced 1s → `PUT /api/projects/{id}/context/draft`). "Publish" button with confirmation: "This will rebriefing all N agents." Shows published/draft diff when both exist. |
| **Documents** | File upload zone + list of uploaded documents. Each: filename, size, processing status (pending/ready), date, delete button. |

---

## 16. Settings Pages

### 16.1 Git Providers (`/settings/git`)

- List of connected Git providers (cards).
- Each card: provider icon (GitHub/GitLab), display name, status, repo count, last verified date.
- "Connect GitHub" / "Connect GitLab" buttons → form with PAT input.
- Expand a connection to see repositories with webhook status (configured/not configured).
- "Configure Webhook" button per repo.
- "Test Connection" button.
- "Delete Connection" with confirmation.

### 16.2 MCP Connections (`/settings/mcp`)

- List of MCP connections (cards).
- Each card: name, server URL, status, tool count.
- "Add Connection" button → form: name, server URL, auth type, auth config.
- Expand a connection to see discovered tools (name + description list).
- "Test" and "Rediscover Tools" buttons.
- "Delete Connection" with confirmation.

### 16.3 Usage & Cost (`/settings/usage`)

Data from `GET /api/usage`.

Layout:
- **Top bar:** Monthly budget progress bar. "$42.50 / $50.00 (85%)" with color indicator (green < 70%, yellow 70-90%, red > 90%). "Edit Budget" button.
- **Summary cards:** Total cost, total input tokens, total output tokens (for the period).
- **By model breakdown:** Table showing Sonnet vs. Opus cost and token usage.
- **By artifact breakdown:** Scrollable table of artifacts sorted by cost descending.
- **Daily trend:** Simple bar chart of daily cost. (MVP: table or CSS bars — no heavy charting library.)
- **Period selector:** Tabs for Day / Week / Month.

---

## 17. Error Handling & Loading States

### 17.1 Loading States

All data-fetching components use skeleton loaders (shadcn/ui `<Skeleton>`) matching the layout of the loaded content. No spinners except in buttons during mutations.

| Component | Loading Pattern |
|---|---|
| Project list | Grid of skeleton cards (3 items) |
| Artifact list | Skeleton table rows (5 items) |
| Agent grid | Grid of skeleton cards (6 items) |
| Artifact review | Skeleton content block + sidebar |
| Heartbeat | Skeleton step list + progress bar |

### 17.2 Error States

| Error Type | Handling |
|---|---|
| Network error (fetch failed) | TanStack Query shows retry button after 3 failed attempts. Toast: "Connection lost. Retrying..." |
| 404 Not Found | Dedicated `not-found.tsx` page with "Go Back" link |
| 400/422 Validation | Inline field errors (forms) or toast with error message |
| 429 Budget Exceeded | Persistent banner: "Monthly budget reached. [Increase Budget]" |
| 500 Server Error | Toast: "Something went wrong. Please try again." with retry button |

### 17.3 Optimistic Updates

Critical mutations use optimistic updates for instant feedback:

| Mutation | Optimistic Behavior |
|---|---|
| Approve artifact | Immediately update status badge to "Approved" in the list and detail view. Roll back on error. |
| Cancel artifact | Immediately update status badge to "Cancelled." Roll back on error. |
| Archive agent | Immediately remove from the roster grid. Roll back on error. |

---

## 18. Responsive Design

### 18.1 Breakpoints

| Breakpoint | Width | Behavior |
|---|---|---|
| `sm` | ≥ 640px | Mobile-optimized (single column) |
| `md` | ≥ 768px | Tablet (sidebar collapses to icon-only) |
| `lg` | ≥ 1024px | Desktop (full sidebar + content) |
| `xl` | ≥ 1280px | Wide desktop (review sidebar visible by default) |

### 18.2 Key Responsive Behaviors

| Component | < md | md-lg | > lg |
|---|---|---|---|
| Sidebar | Bottom nav bar | Icon-only sidebar | Full sidebar |
| Roster grid | 1 column | 2 columns | 3 columns |
| Artifact review | Stacked (content → sidebar below) | Content + collapsible sidebar | Content + persistent sidebar |
| Diff viewer | Unified only (side-by-side disabled) | Both modes available | Both modes available |
| Smart Brief form | Full width, stacked fields | Full width, stacked fields | 2-column layout for shorter fields |

---

## 19. Accessibility

### 19.1 Standards

Target: WCAG 2.1 Level AA. Key requirements:

- **Color contrast:** All text meets 4.5:1 ratio (AA). Large text meets 3:1.
- **Keyboard navigation:** All interactive elements are focusable and operable via keyboard. Tab order follows visual order.
- **Screen reader:** All non-text content has `aria-label` or `alt` text. Status changes (toasts, heartbeat updates) use `aria-live` regions.
- **Focus management:** Modal dialogs trap focus. Closing returns focus to the trigger element. Route changes move focus to the page heading.
- **Reduced motion:** `prefers-reduced-motion` media query disables all CSS animations/transitions.

### 19.2 Component-Specific Considerations

| Component | Consideration |
|---|---|
| Floating comment toolbar | `role="toolbar"`, `aria-label="Comment on selection"`. Focus moves to toolbar on activation. |
| Heartbeat steps | `aria-live="polite"` region updates on step changes. `role="progressbar"` on the progress bar. |
| Diff viewer | Ensure removed/added text is distinguishable without color (strikethrough for removed, underline for added). |
| Status badges | Include `aria-label` with full status text, not just color. |
| Toast notifications | `role="alert"` for errors, `role="status"` for success/info. |

---

## 20. Performance Budget

| Metric | Target | Strategy |
|---|---|---|
| **First Contentful Paint** | < 1.5s | Server components for shell, streaming SSR |
| **Time to Interactive** | < 3.0s | Code-split by route, lazy-load heavy components |
| **Bundle size (initial)** | < 150 KB (gzipped) | Tree-shaking, dynamic imports for diff viewer and markdown renderer |
| **Largest Contentful Paint** | < 2.5s | Skeleton loaders for perceived performance |

### Heavy Components (Lazy-Loaded)

| Component | Approximate Size | Load Trigger |
|---|---|---|
| `react-diff-viewer-continued` | ~40 KB | When user navigates to diff view |
| `react-markdown` + plugins | ~35 KB | When user views prose content |
| Usage charts (if added) | ~20 KB | When user navigates to usage page |

```typescript
const ProseDiffViewer = dynamic(() => import("@/features/artifacts/prose-diff-viewer"), {
  loading: () => <Skeleton className="h-96" />,
});
```

---

## 21. Verification Checklist

- [ ] All 44 API endpoints from TDD-04 have corresponding frontend API client methods
- [ ] TanStack Query keys are unique per resource and invalidated correctly on mutations and WebSocket events
- [ ] Heartbeat polling activates only when `status === "drafting"` and stops when status changes
- [ ] Sufficiency check issues are displayed inline next to the correct form fields with `matched_text` highlighting
- [ ] Delegation preview shows the plan (template, waves, agents, cost) and allows confirmation or override
- [ ] Prose diff viewer supports both unified and side-by-side modes with correct design tokens for light and dark
- [ ] Contextual commenting: text selection triggers floating toolbar, comment submission calls iterate endpoint with character offsets
- [ ] Code artifact review page shows PR link prominently, no in-app diff, and explains approval is via PR merge
- [ ] WebSocket events trigger TanStack Query invalidation (not direct state mutation) for the correct query keys
- [ ] Toast notifications appear for: artifact ready, execution failed, budget warning, agent status change
- [ ] Onboarding flow redirects first-time users and creates roster via `POST /api/onboarding`
- [ ] Dark mode toggles correctly via CSS variables on the `.dark` class, persisted to `localStorage`
- [ ] All destructive actions (delete project, archive agent, cancel artifact) require a confirmation dialog
- [ ] Responsive layout: sidebar collapses on mobile, review sidebar stacks below content, diff viewer forces unified on small screens
- [ ] Accessibility: keyboard navigation works for all interactive elements, `aria-live` regions for dynamic content, focus management for modals
- [ ] Loading states use skeleton loaders matching the content layout, not spinners
- [ ] Optimistic updates for approve/cancel mutations with rollback on error
