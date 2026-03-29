# `artifacts/sufficiency-feedback` & `artifacts/smart-brief-form`

> UI components for the code-factory task creation flow: a multi-step smart brief form and inline sufficiency validation feedback.

**Source:**
- [`frontend/features/artifacts/smart-brief-form.tsx`](frontend/features/artifacts/smart-brief-form.tsx)
- [`frontend/features/artifacts/sufficiency-feedback.tsx`](frontend/features/artifacts/sufficiency-feedback.tsx)

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Components](#components)
  - [SmartBriefForm](#smartbriefform)
  - [FieldIssues](#fieldissues)
  - [SufficiencySummary](#sufficiencysummary)
- [Types & Interfaces](#types--interfaces)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [Related Modules](#related-modules)
- [Changelog](#changelog)

---

## Overview

This module provides two cooperating React components that together implement the three-step code-factory artifact creation flow:

1. **`SmartBriefForm`** — A multi-step form where a user selects a task type, fills adaptive fields, triggers server-side sufficiency validation (`POST /api/artifacts/{id}/validate`), and ultimately delegates the artifact to an AI agent team.
2. **`FieldIssues`** / **`SufficiencySummary`** — Inline and summary-level display of `SufficiencyIssue` objects returned by the validation endpoint, including optional `matched_text` highlighting within the current field value.

### When to Use This Module

- Rendering the "New Artifact" form inside a project context.
- Displaying per-field sufficiency feedback returned from the validation API next to any form input.
- Showing an overall pass/fail sufficiency summary bar after validation completes.

### When NOT to Use This Module

- Displaying artifact detail or execution status after delegation — use the artifact detail page instead.
- Consuming or mutating artifact data outside of this creation flow — use the hooks in `lib/hooks/use-artifacts` directly.
- Rendering sufficiency data in a non-form context where the `field` correlation is not needed.

---

## Quick Start

### Import

```typescript
import { SmartBriefForm } from '@/features/artifacts/smart-brief-form';
import { FieldIssues, SufficiencySummary } from '@/features/artifacts/sufficiency-feedback';
```

### Minimal Example

```tsx
// Render the full creation form inside a project page
export default function NewArtifactPage({ params }: { params: { projectId: string } }) {
  return (
    <main className="max-w-2xl mx-auto p-6">
      <h1 className="text-xl font-semibold mb-4">New Task</h1>
      <SmartBriefForm projectId={params.projectId} />
    </main>
  );
}
```

```tsx
// Render per-field feedback alongside a standalone input
import { FieldIssues } from '@/features/artifacts/sufficiency-feedback';
import type { SufficiencyIssue } from '@/lib/types/api';

const issues: SufficiencyIssue[] = [
  {
    field: 'title',
    severity: 'warning',
    issue: 'Title is too vague',
    suggestion: 'Include the affected module and expected behaviour.',
    matched_text: 'fix bug',
  },
];

<FieldIssues issues={issues} fieldValue="fix bug in login" />
```

---

## Components

### `SmartBriefForm`

The top-level form component for creating a code-factory artifact. Manages the full creation lifecycle: task-type selection → field completion → server-side validation → delegation preview → confirmed delegation.

```tsx
<SmartBriefForm projectId={projectId} />
```

#### Props

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `projectId` | `string` | Yes | — | The ID of the project under which the artifact will be created. Used for API calls and post-delegation navigation. |

#### Behaviour

**Task type selection**

Eight task types are available. Each maps to a DAG template used by the agent team:

| Task Type ID | Label | DAG Template |
|---|---|---|
| `feature` | Feature | `full_feature` |
| `bug_fix` | Bug Fix | `bug_fix` |
| `refactor` | Refactor | `refactor` |
| `security` | Security | `security_fix` |
| `performance` | Performance | `performance` |
| `infra` | Infrastructure | `infra_devops` |
| `api` | API Integration | `api_integration` |
| `architecture` | Architecture | `architecture` |

**Adaptive fields**

- `severity` and `reproduction_steps` fields are rendered only when `task_type === "bug_fix"`.
- `affected_services` field is rendered only when `task_type === "infra"`.
- `context` is auto-populated from `project.primary_language` and `project.framework` if left empty.

**Three-step flow**

1. **Validate** (`handleSubmit` → `handleValidate`): Creates the artifact via `POST /api/artifacts` if not yet created, then calls `POST /api/artifacts/{id}/validate`. Populates `sufficiency` state. The Delegate button is enabled only when `sufficiency.eligible === true` and no critical issues exist.
2. **Delegate preview** (`handleDelegate`): Calls `POST /api/artifacts/{id}/delegate` with `{ confirm: false }`. Opens `DelegatePreview` modal with the returned plan.
3. **Confirm delegation** (`handleConfirmDelegation`): Calls `POST /api/artifacts/{id}/delegate` with `{ confirm: true }`. Navigates to the artifact detail page on success.

#### Form Schema

Validated with `zod`. Fields and constraints:

| Field | Type | Constraints |
|---|---|---|
| `artifact_type` | `"code"` (literal) | Fixed |
| `task_type` | `string` | min length 1 |
| `title` | `string` | min 1, max 200 |
| `goal` | `string` | max 1000 |
| `context` | `string` | max 3000 |
| `description` | `string` | min 10, max 5000 |
| `severity` | `string` | — |
| `reproduction_steps` | `string` | max 2000 |
| `affected_services` | `string` | max 500 |
| `max_budget_usd` | `number` | min 0.5 |

#### Full Example

```tsx
import { SmartBriefForm } from '@/features/artifacts/smart-brief-form';

export function CreateArtifactPanel({ projectId }: { projectId: string }) {
  return (
    <section className="rounded-lg border p-6">
      <h2 className="mb-4 text-lg font-semibold">Create Artifact</h2>
      <SmartBriefForm projectId={projectId} />
    </section>
  );
}
```

---

### `FieldIssues`

Renders a stacked list of `SufficiencyIssue` items inline below a form input. Each issue displays an icon, the issue message, an optional suggestion, and optionally highlights `matched_text` within the current `fieldValue`.

```tsx
export function FieldIssues({ issues, fieldValue }: FieldIssuesProps)
```

#### Props

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `issues` | `SufficiencyIssue[]` | Yes | — | Issues targeting this specific field, as returned by the validation API. |
| `fieldValue` | `string` | No | `undefined` | Current value of the associated form field. Used to locate and highlight `matched_text`. |

#### Returns

`null` when `issues` is empty. Otherwise renders a `div` containing one entry per issue.

**Severity styling:**

| Severity | Icon | Visual style |
|---|---|---|
| `critical` | `AlertCircle` | Danger colours, destructive badge |
| `warning` | `AlertTriangle` | Warning colours, outline badge |
| `info` | `Info` | Muted tertiary colours, secondary badge |

> **Note:** The `info` severity level is handled in the component's internal `severityConfig` for display purposes, but the `SufficiencyIssue` type from the API currently only emits `"critical"` or `"warning"`.

#### Example

```tsx
import { FieldIssues } from '@/features/artifacts/sufficiency-feedback';

// Inside a form, below a <Textarea id="description" />
<FieldIssues
  issues={issuesByField.get('description') ?? []}
  fieldValue={watch('description')}
/>
```

---

### `SufficiencySummary`

Renders a single-line summary bar reflecting overall validation status. Shows critical and warning counts as `Badge` elements when issues exist, or a green "ready to delegate" indicator when the brief is fully sufficient.

```tsx
export function SufficiencySummary({ isEligible, issues }: SufficiencySummaryProps)
```

#### Props

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `isEligible` | `boolean` | Yes | — | Whether the artifact passed validation (`SufficiencyResponse.eligible`). |
| `issues` | `SufficiencyIssue[]` | Yes | — | Full list of issues from the validation response. Used to compute critical and warning counts. |

#### Behaviour

- `issues.length === 0 && isEligible === true`: Renders a green success bar — "Brief is sufficient. Ready to delegate."
- Otherwise: Renders a muted bar with `Badge` counts for critical and warning issues, plus an advisory message. Critical issues display "Fix critical issues before delegating." Warning-only issues display "Warnings are advisory — you can still delegate."

#### Example

```tsx
import { SufficiencySummary } from '@/features/artifacts/sufficiency-feedback';

{sufficiency && (
  <SufficiencySummary
    isEligible={sufficiency.eligible}
    issues={sufficiency.issues}
  />
)}
```

---

## Types & Interfaces

### `SufficiencyResponse`

Returned by `POST /api/artifacts/{id}/validate`.

```typescript
export interface SufficiencyResponse {
  eligible: boolean;
  score: number;
  issues: SufficiencyIssue[];
}
```

| Field | Description |
|---|---|
| `eligible` | `true` if the artifact has sufficient detail for delegation to proceed. |
| `score` | Numeric sufficiency score. |
| `issues` | List of per-field issues found during validation. |

---

### `SufficiencyIssue`

A single validation finding targeting one form field.

```typescript
export interface SufficiencyIssue {
  field: string;
  severity: "critical" | "warning";
  matched_text: string;
  issue: string;
  suggestion: string;
}
```

| Field | Description |
|---|---|
| `field` | The form field name this issue relates to (e.g. `"title"`, `"description"`). |
| `severity` | `"critical"` blocks delegation; `"warning"` is advisory. |
| `matched_text` | Substring of the field value that triggered this issue. Used for highlighting. |
| `issue` | Human-readable issue message displayed in the issue chip. |
| `suggestion` | Actionable suggestion shown below the issue message. |

---

### `SmartBriefFormProps`

```typescript
interface SmartBriefFormProps {
  projectId: string;
}
```

---

### `FieldIssuesProps`

```typescript
interface FieldIssuesProps {
  issues: SufficiencyIssue[];
  fieldValue?: string;
}
```

---

### `SufficiencySummaryProps`

```typescript
interface SufficiencySummaryProps {
  isEligible: boolean;
  issues: SufficiencyIssue[];
}
```

---

## Error Handling

Errors during API calls are caught within `SmartBriefForm` and surfaced via `sonner` toast notifications. No errors are thrown to the caller.

| Operation | Failure behaviour |
|---|---|
| Artifact creation (`createArtifact.mutateAsync`) | `toast.error` with `error.message` or `"Validation failed"` |
| Validate (`api.artifacts.validate`) | `toast.error` with `error.message` or `"Validation failed"` |
| Delegate preview (`api.artifacts.delegate`) | `toast.error` with `error.message` or `"Failed to generate plan"` |
| Confirm delegation (`api.artifacts.delegate`) | `toast.error` with `error.message` or `"Delegation failed"` |

### Error Handling Example

```tsx
// SmartBriefForm handles errors internally — no try/catch needed at the call site.
// Errors appear as toast notifications to the user.
<SmartBriefForm projectId={projectId} />
```

---

## Testing

### Test Helpers

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SmartBriefForm } from '@/features/artifacts/smart-brief-form';

// Minimal wrapper — provide react-query QueryClient and router mocks
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function renderForm(projectId = 'proj_123') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SmartBriefForm projectId={projectId} />
    </QueryClientProvider>
  );
}
```

### Mocking

```tsx
// Mock the API module used by SmartBriefForm
jest.mock('@/lib/api', () => ({
  api: {
    artifacts: {
      validate: jest.fn().mockResolvedValue({
        eligible: true,
        score: 0.92,
        issues: [],
      }),
      delegate: jest.fn().mockResolvedValue({
        plan: { steps: [], estimated_cost_usd: 1.2 },
      }),
    },
  },
}));

// Test FieldIssues in isolation
import { FieldIssues } from '@/features/artifacts/sufficiency-feedback';
import type { SufficiencyIssue } from '@/lib/types/api';

const mockIssues: SufficiencyIssue[] = [
  {
    field: 'description',
    severity: 'critical',
    issue: 'Description is too short',
    suggestion: 'Provide at least 50 characters of detail.',
    matched_text: 'fix it',
  },
];

render(<FieldIssues issues={mockIssues} fieldValue="just fix it please" />);
expect(screen.getByText('Description is too short')).toBeInTheDocument();
expect(screen.getByText('Provide at least 50 characters of detail.')).toBeInTheDocument();
```

---

## Related Modules

| Module | Relationship |
|--------|-------------|
| [`lib/hooks/use-artifacts`](../../lib/hooks/use-artifacts.ts) | Provides `useCreateArtifact`, `useValidateArtifact`, `useDelegateArtifact` hooks consumed by `SmartBriefForm`. |
| [`lib/hooks/use-projects`](../../lib/hooks/use-projects.ts) | Provides `useProjectDetail` for auto-populating technical context. |
| [`features/artifacts/delegate-preview`](./delegate-preview.tsx) | Modal component rendered by `SmartBriefForm` after a successful preview delegation call. |
| [`lib/types/api`](../../lib/types/api.ts) | Source of truth for `SufficiencyIssue`, `SufficiencyResponse`, `DelegatePlan`, and `DelegatePreviewResponse` types. |

---

## Changelog

| Version | Change | Type |
|---------|--------|------|
| Current | `SufficiencyResponse.is_sufficient` renamed to `eligible`; `score` field added; `suggestions: string[]` removed | Breaking |
| Current | `SufficiencyIssue.message` renamed to `issue`; `suggestion` field added as a dedicated property; `severity` narrowed from `"critical" \| "warning" \| "info"` to `"critical" \| "warning"`; `matched_text` changed from `string \| null` to `string` | Breaking |
| Current | `FieldIssues` now renders `issue.suggestion` below the issue message when present | Feature |