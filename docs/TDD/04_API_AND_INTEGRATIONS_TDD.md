# Phase 4 — API Contracts & Integrations (TDD)

> **Document type:** Technical Design Document
> **Status:** Draft
> **Source of truth:** `docs/VISION_2.0.md`, `docs/TDD/01_PRD_AND_WORKFLOWS.md`, `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md`, `docs/TDD/03_AI_AGENT_ENGINE_TDD.md`
> **Scope:** REST API endpoint specs (routes, payloads, responses), GitHub/GitLab integration, MCP integration, webhook handling. No database schema (see TDD-02), no prompt engineering (see TDD-03), no frontend (see TDD-05).

---

## Architectural Decisions Log

| ID | Decision | Rationale |
|---|---|---|
| **AD-14** | GitHub/GitLab auth via PAT only (no OAuth) | Ship fast. No redirect flow, no callback URL, no OAuth app registration. User pastes a token. Works immediately. OAuth deferred to post-MVP. |
| **AD-15** | Artifact files served via backend proxy (not pre-signed URLs) | Simpler for the frontend — one API call, no S3 network dependency. Backend fetches from S3 and streams to client. |
| **AD-16** | Cursor-based pagination | More robust than offset/limit for real-time data where items can be inserted/deleted between page fetches. Uses opaque cursor tokens. |
| **AD-17** | Auto-configure GitHub webhooks via API | Backend registers the webhook on the repo automatically when the user connects. Requires `admin:repo_hook` scope on the PAT. Seamless UX. |

---

## 1. API Conventions

### 1.1 Base URL

```
http://localhost:8000/api
```

No version prefix for MVP (`/api/`, not `/api/v1/`). Version prefix added when breaking changes require it.

### 1.2 Authentication

**MVP: No authentication.** Single-tenant, hardcoded `workspace_id = 1` (AD-1 from TDD-02). All endpoints are public. CORS restricts to `http://localhost:3000`.

A `get_workspace_id()` dependency is used in every route handler. Today it returns `"1"`. When auth is added, it extracts the workspace from the JWT.

```python
async def get_workspace_id() -> str:
    """MVP: hardcoded. Post-MVP: extract from JWT."""
    return "1"
```

### 1.3 Pagination (Cursor-Based)

All list endpoints use cursor-based pagination with this query parameter contract:

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | `integer` | 20 | Max items per page (1-100) |
| `cursor` | `string` | `null` | Opaque cursor from previous response. Omit for first page. |

**Response envelope:**

```json
{
  "items": [ ... ],
  "next_cursor": "eyJpZCI6IjEyMyIsImNyZWF0ZWRfYXQiOiIyMDI2LTAzLTI2VDEwOjAwOjAwWiJ9",
  "has_more": true
}
```

The cursor is a base64-encoded JSON object containing the sort key(s) of the last item (e.g., `{"id": "abc", "created_at": "2026-03-26T10:00:00Z"}`). The client treats it as opaque — never parses it.

**SQL implementation:**

```sql
SELECT * FROM artifacts
WHERE project_id = :project_id
  AND (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit + 1;  -- fetch one extra to determine has_more
```

### 1.4 Error Response Format

All errors use a consistent JSON envelope:

```json
{
  "error": {
    "code": "ARTIFACT_NOT_FOUND",
    "message": "Artifact with id 'abc-123' not found.",
    "details": {}
  }
}
```

| HTTP Status | When |
|---|---|
| `400` | Invalid request payload, validation failure |
| `404` | Resource not found |
| `409` | Conflict (e.g., artifact already approved, duplicate) |
| `413` | Payload too large (file uploads) |
| `422` | Unprocessable entity (Pydantic validation) |
| `429` | Budget ceiling reached (monthly or per-artifact) |
| `500` | Internal server error |

### 1.5 Timestamp Format

All timestamps are ISO 8601 in UTC: `"2026-03-26T10:30:00Z"`.

### 1.6 ID Format

All IDs are UUID v4 strings: `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`.

---

## 2. Onboarding

### `POST /api/onboarding`

First-time setup. Generates a default agent roster based on company context.

**Request:**
```json
{
  "company_name": "Acme SaaS",
  "domain_description": "B2B project management tool for small teams",
  "tech_stack": "Next.js, FastAPI, PostgreSQL",
  "team_size": 3,
  "use_case": "both"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company_name` | `string` | Yes | |
| `domain_description` | `string` | Yes | Industry, product, goals |
| `tech_stack` | `string` | No | Tech stack (pre-fills agent context) |
| `team_size` | `integer` | No | Company headcount |
| `use_case` | `string` | Yes | `"code"`, `"content"`, or `"both"` |

**Response: `201 Created`**
```json
{
  "workspace": {
    "id": "uuid",
    "name": "Acme SaaS",
    "onboarding_completed": true
  },
  "agents": [
    {
      "id": "uuid",
      "name": "Product Expert",
      "specialization": "Product strategy, user flows, and requirements for B2B SaaS",
      "status": "learning",
      "readiness_score": 0,
      "progression_level": "apprenti"
    }
  ]
}
```

**Behavior:**
1. Updates the workspace row with `company_name`, `domain_description`, `tech_stack`.
2. Generates a roster via LLM call (Haiku — reads the company context, outputs agent names + specializations). Fallback: hardcoded default roster if LLM fails.
3. Creates agent rows. Each enters `learning` status.
4. Enqueues `execute_agent_learning` Celery tasks for all agents.
5. Sets `workspace.onboarding_completed = true`.

**Error:**
- `409 Conflict` if `workspace.onboarding_completed` is already `true`.

---

## 3. Roster (Agents)

### `GET /api/roster`

List all agents in the workspace roster.

**Query params:** `limit`, `cursor`, `status` (optional filter: `learning`, `ready`, `working`, `reflecting`), `include_archived` (boolean, default `false`).

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Content Writer",
      "specialization": "Technical documentation and blog content",
      "description": "Specializes in clear, concise technical writing for developer audiences.",
      "status": "ready",
      "readiness_score": 90,
      "progression_level": "opérationnel",
      "model_tier": "sonnet",
      "completed_artifacts": 12,
      "avg_quality_score": 4.2,
      "archived_at": null,
      "created_at": "2026-03-01T10:00:00Z"
    }
  ],
  "next_cursor": "...",
  "has_more": false
}
```

---

### `GET /api/roster/{agent_id}`

Get full agent detail including skills summary.

**Response: `200 OK`**
```json
{
  "id": "uuid",
  "name": "Content Writer",
  "specialization": "Technical documentation and blog content",
  "description": "...",
  "system_prompt": "...",
  "status": "ready",
  "readiness_score": 90,
  "progression_level": "opérationnel",
  "model_tier": "sonnet",
  "tools": ["web_search", "web_browser", "vector_search", "file_read", "file_write"],
  "completed_artifacts": 12,
  "avg_quality_score": 4.2,
  "last_reflection_at": "2026-03-20T14:00:00Z",
  "archived_at": null,
  "skills_summary": {
    "total_skill_tokens": 4200,
    "total_learning_tokens": 1100,
    "budget_used_pct": 66,
    "skill_count": 5,
    "learning_count": 3
  },
  "created_at": "2026-03-01T10:00:00Z",
  "updated_at": "2026-03-20T14:00:00Z"
}
```

---

### `POST /api/roster`

Add a new agent to the roster.

**Request:**
```json
{
  "name": "SEO Specialist",
  "specialization": "Search engine optimization and content strategy",
  "description": "Focuses on keyword research, on-page SEO, and content optimization.",
  "model_tier": "sonnet"
}
```

**Response: `201 Created`** — Returns the full agent object (status = `learning`).

**Behavior:** Creates the agent, enqueues `execute_agent_learning`.

---

### `PATCH /api/roster/{agent_id}`

Update agent configuration.

**Request (partial update — all fields optional):**
```json
{
  "name": "Technical Writer",
  "specialization": "API documentation and developer guides",
  "description": "...",
  "model_tier": "opus"
}
```

**Response: `200 OK`** — Returns updated agent.

---

### `DELETE /api/roster/{agent_id}`

Soft-archive an agent. Sets `archived_at` timestamp. Agent is excluded from auto-assembly and hidden from active roster.

**Response: `200 OK`**
```json
{
  "id": "uuid",
  "archived_at": "2026-03-26T10:00:00Z"
}
```

---

### `DELETE /api/roster/{agent_id}/permanent`

Hard-delete an agent and all associated data (skills, learnings, workspace). Irreversible.

**Response: `204 No Content`**

---

### `GET /api/roster/{agent_id}/skills`

List all skill and work_learning entries for an agent.

**Query params:** `category` (optional filter: `skill`, `work_learning`, `briefing`).

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "category": "skill",
      "title": "Brand voice: conversational, no corporate jargon",
      "content": "The user's brand voice is...",
      "token_count": 340,
      "source_artifact_id": "uuid-or-null",
      "created_at": "2026-03-15T10:00:00Z",
      "updated_at": "2026-03-15T10:00:00Z"
    }
  ],
  "budget": {
    "used_tokens": 5300,
    "max_tokens": 8000,
    "used_pct": 66
  }
}
```

---

### `GET /api/roster/{agent_id}/learning-profile`

Get the agent's learning profile and knowledge readiness breakdown.

**Response: `200 OK`**
```json
{
  "agent_id": "uuid",
  "readiness_score": 90,
  "readiness_breakdown": {
    "has_skills": { "points": 40, "max": 40, "met": true },
    "has_briefing": { "points": 30, "max": 30, "met": true },
    "onboarding_complete": { "points": 20, "max": 20, "met": true },
    "has_learnings": { "points": 0, "max": 10, "met": false }
  },
  "progression_level": "opérationnel",
  "completed_artifacts": 12,
  "avg_quality_score": 4.2,
  "last_reflection_at": "2026-03-20T14:00:00Z",
  "skill_token_usage": { "used": 5300, "max": 8000 }
}
```

---

### `POST /api/roster/{agent_id}/research`

Trigger autonomous web research on a specific topic.

**Request:**
```json
{
  "topic": "WCAG 2.2 accessibility guidelines for form components"
}
```

**Response: `202 Accepted`**
```json
{
  "message": "Research started.",
  "agent_status": "learning"
}
```

**Behavior:** Sets agent status to `learning`, enqueues a learning Celery task focused on the topic. Agent returns to `ready` when complete.

---

### `POST /api/roster/{agent_id}/reflect`

Manually trigger a reflection cycle.

**Response: `202 Accepted`**
```json
{
  "message": "Reflection started.",
  "agent_status": "reflecting"
}
```

---

### `POST /api/roster/{agent_id}/knowledge`

Upload a document or URL to an agent's knowledge base. Ingests the content and creates skill entries.

**Request:** `Content-Type: multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `binary` | No | A document (PDF, DOCX, TXT, MD). Max 10 MB. |
| `url` | `string` | No | A URL to fetch and ingest. |

One of `file` or `url` must be provided.

**Response: `202 Accepted`**
```json
{
  "message": "Knowledge ingestion started.",
  "agent_status": "learning"
}
```

**Behavior:** The agent enters `learning` status. A Celery task fetches the content (file from upload or page from URL), extracts text, and creates `agent_skills` entries with `category = 'skill'`. Agent returns to `ready` when complete.

---

### `GET /api/roster/{agent_id}/knowledge-recommendations`

Get system-suggested actions to fill knowledge gaps.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "type": "research_topic",
      "title": "React Server Components",
      "reason": "3 recent briefs referenced RSC but this agent has no indexed knowledge on the topic.",
      "suggested_action": "Trigger web research on React Server Components patterns and best practices.",
      "created_at": "2026-03-25T10:00:00Z"
    }
  ]
}
```

**Behavior:** Recommendations are generated during the readiness score computation or after artifact completions. They are stored as lightweight rows (or computed on-the-fly for MVP).

---

### `POST /api/roster/{agent_id}/knowledge-recommendations/{rec_id}/apply`

Apply a knowledge recommendation (triggers background research).

**Response: `202 Accepted`**
```json
{
  "message": "Recommendation applied. Research started.",
  "agent_status": "learning"
}
```

**Behavior:** Equivalent to calling `POST /api/roster/{agent_id}/research` with the recommendation's topic. Marks the recommendation as applied.

---

### `POST /api/roster/{agent_id}/knowledge-recommendations/{rec_id}/dismiss`

Dismiss a knowledge recommendation.

**Response: `200 OK`**
```json
{
  "id": "uuid",
  "dismissed": true
}
```

---

### `GET /api/roster/readiness/global`

Global knowledge readiness summary across all active agents.

**Response: `200 OK`**
```json
{
  "total_agents": 8,
  "by_readiness": {
    "sufficient": 5,
    "partial": 2,
    "insufficient": 1
  },
  "by_status": {
    "ready": 6,
    "learning": 1,
    "reflecting": 1,
    "working": 0
  },
  "avg_readiness_score": 78,
  "agents_needing_attention": [
    {
      "agent_id": "uuid",
      "agent_name": "SEO Specialist",
      "readiness_score": 20,
      "issue": "No core skills — initial learning may have failed."
    }
  ]
}
```

---

## 4. Projects

### `GET /api/projects`

**Query params:** `limit`, `cursor`.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Q3 Product Launch",
      "description": "...",
      "artifact_count": 8,
      "brief_status": "published",
      "created_at": "2026-03-01T10:00:00Z"
    }
  ],
  "next_cursor": "...",
  "has_more": false
}
```

`artifact_count` is computed via subquery. `brief_status` is `"draft"`, `"published"`, or `"none"`.

---

### `POST /api/projects`

**Request:**
```json
{
  "name": "Q3 Product Launch",
  "description": "Launch the new enterprise pricing tier."
}
```

**Response: `201 Created`** — Returns the full project object.

---

### `PATCH /api/projects/{id}`

**Request (partial):**
```json
{
  "name": "Q3 Enterprise Launch",
  "description": "..."
}
```

**Response: `200 OK`**

---

### `DELETE /api/projects/{id}`

Deletes the project and all associated artifacts, versions, documents, and comments (cascade). Requires confirmation header:

```
X-Confirm-Delete: true
```

**Response: `204 No Content`**

---

### `GET /api/projects/{id}/context`

Get the project brief (draft + published state).

**Response: `200 OK`**
```json
{
  "draft": "Working draft text...",
  "published": "The published brief text...",
  "published_at": "2026-03-15T10:00:00Z",
  "fingerprint": "sha256-abc123..."
}
```

---

### `PUT /api/projects/{id}/context/draft`

Save the working draft (auto-save from frontend).

**Request:**
```json
{
  "content": "Updated draft text..."
}
```

**Response: `200 OK`**

---

### `POST /api/projects/{id}/context/publish`

Publish the draft brief. Triggers rebriefing of all roster agents.

**Response: `200 OK`**
```json
{
  "published": "The published brief text...",
  "published_at": "2026-03-26T10:00:00Z",
  "fingerprint": "sha256-def456...",
  "agents_rebriefed": 8
}
```

**Behavior:**
1. Copies `brief_draft` → `brief_published`.
2. Computes SHA-256 fingerprint.
3. Creates/updates `briefing` skill entries for all active roster agents (see TDD-03 Section 11.3).
4. Returns count of rebriefed agents.

---

## 5. Artifacts

### `POST /api/artifacts`

Create a new artifact from the Smart Brief form.

**Request:**
```json
{
  "project_id": "uuid",
  "artifact_type": "prose",
  "title": "Q3 Competitive Analysis",
  "goal": "Identify top 3 competitor weaknesses we can exploit in messaging.",
  "target_audience": "Exec team, Series A investors",
  "context": "Focus on US market, B2B SaaS only.",
  "description": "Compare Notion, Coda, Confluence on pricing, collaboration, AI features. Include recommendation matrix.",
  "max_budget_usd": 5.00,
  "git_repo_url": null,
  "git_base_branch": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `project_id` | `string` | Yes | |
| `artifact_type` | `string` | Yes | `"prose"` or `"code"` |
| `title` | `string` | Yes | |
| `goal` | `string` | No | |
| `target_audience` | `string` | No | |
| `context` | `string` | No | |
| `description` | `string` | Yes | The main brief body |
| `max_budget_usd` | `number` | No | Default: 5.00 |
| `git_repo_url` | `string` | No | Required for code artifacts |
| `git_base_branch` | `string` | No | Default: repo's default branch |

**Response: `201 Created`**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "artifact_type": "prose",
  "title": "Q3 Competitive Analysis",
  "goal": "...",
  "target_audience": "...",
  "context": "...",
  "description": "...",
  "status": "drafting",
  "max_budget_usd": 5.00,
  "total_cost_usd": 0.00,
  "current_version": 0,
  "git_repo_url": null,
  "git_base_branch": null,
  "git_feature_branch": null,
  "git_pr_url": null,
  "git_pr_number": null,
  "approved_at": null,
  "cancelled_at": null,
  "created_at": "2026-03-26T10:00:00Z",
  "updated_at": "2026-03-26T10:00:00Z"
}
```

All artifact responses (POST, GET, PATCH) return the same full object shape. Git fields are `null` for prose artifacts.

**Behavior:** Creates the artifact row only. Does NOT trigger execution. The client must call the sufficiency check and then the delegate endpoint.

---

### `POST /api/artifacts/{id}/validate`

Run the sufficiency check on the artifact's brief.

**Response: `200 OK`**
```json
{
  "eligible": false,
  "score": 62,
  "issues": [
    {
      "severity": "critical",
      "field": "description",
      "matched_text": "Write a competitive analysis of SaaS.",
      "issue": "No specific competitors named. No market scope defined.",
      "suggestion": "Which specific competitors? US or EU market?"
    }
  ]
}
```

See TDD-03 Section 1 for the full sufficiency check engine spec.

---

### `POST /api/artifacts/{id}/delegate`

Trigger execution. Runs the DAG router, shows the plan for confirmation, and enqueues execution.

**Request (optional — for overriding the auto-assembled plan):**
```json
{
  "confirm": true,
  "overrides": {
    "template_id": null,
    "slot_assignments": null
  }
}
```

If `confirm` is `false` or omitted, returns the plan for preview without starting execution.

**Response (preview, `confirm: false`): `200 OK`**
```json
{
  "plan": {
    "template_id": "content_research",
    "template_name": "Research & Content",
    "waves": [
      {
        "wave_number": 1,
        "label": "Researching & gathering data",
        "agents": [
          { "slot_id": "researcher", "agent_id": "uuid", "agent_name": "Research Analyst" },
          { "slot_id": "framework_designer", "agent_id": "uuid", "agent_name": "Product Expert" }
        ]
      },
      {
        "wave_number": 2,
        "label": "Drafting the deliverable",
        "agents": [
          { "slot_id": "writer", "agent_id": "uuid", "agent_name": "Strategy Analyst" }
        ]
      },
      {
        "wave_number": 3,
        "label": "Editorial review",
        "agents": [
          { "slot_id": "editor", "agent_id": "uuid", "agent_name": "Content Writer" }
        ]
      }
    ],
    "estimated_cost_usd": 0.65,
    "estimated_waves": 3
  }
}
```

**Response (confirmed, `confirm: true`): `202 Accepted`**
```json
{
  "artifact_id": "uuid",
  "status": "drafting",
  "execution_wave_id": "uuid",
  "plan": { ... }
}
```

**Behavior on confirm:**
1. Creates `execution_wave` row with `dag_plan`, `assembled_team`, `step_labels`.
2. Sets `artifact.status = 'drafting'`.
3. Enqueues `execute_artifact_dag(execution_wave_id)` Celery task.

**Errors:**
- `400` if brief has unresolved critical issues (sufficiency check not passed).
- `429` if monthly budget ceiling reached.

---

### `GET /api/artifacts/{id}`

Get artifact with its current version summary.

**Response: `200 OK`**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "artifact_type": "prose",
  "title": "Q3 Competitive Analysis",
  "goal": "...",
  "target_audience": "...",
  "context": "...",
  "description": "...",
  "status": "in_review",
  "max_budget_usd": 5.00,
  "total_cost_usd": 0.42,
  "current_version": 2,
  "git_repo_url": null,
  "git_pr_url": null,
  "created_at": "2026-03-26T10:00:00Z",
  "updated_at": "2026-03-26T10:35:00Z",
  "approved_at": null,
  "cancelled_at": null
}
```

---

### `GET /api/artifacts/{id}/status`

Lightweight polling endpoint for the heartbeat UI. Returns execution progress.

**Response: `200 OK`**
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

When `status` is not `"drafting"` or there is no active wave, the `execution` field is `null`.

**Polling interval:** Frontend polls every 3 seconds while `status == "drafting"`.

---

### `GET /api/artifacts/{id}/versions`

List all versions of an artifact.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "version_number": 2,
      "file_manifest": ["report.md"],
      "token_cost_usd": 0.18,
      "input_tokens": 3200,
      "output_tokens": 1800,
      "assumptions": [
        { "text": "US market only", "agent": "Research Analyst" }
      ],
      "sources": [
        { "url": "https://example.com/pricing", "title": "Competitor Pricing Page", "agent": "Research Analyst" }
      ],
      "created_at": "2026-03-26T10:35:00Z"
    },
    {
      "id": "uuid",
      "version_number": 1,
      "file_manifest": ["report.md"],
      "token_cost_usd": 0.24,
      "input_tokens": 4100,
      "output_tokens": 2200,
      "assumptions": [ ... ],
      "sources": [ ... ],
      "created_at": "2026-03-26T10:30:00Z"
    }
  ]
}
```

Ordered by `version_number DESC` (most recent first). No pagination — artifact versions are bounded (typically < 10).

---

### `GET /api/artifacts/{id}/versions/{version_number}/files/{file_path:path}`

Download a single file from an artifact version. Backend proxies from S3 (AD-15).

**Response: `200 OK`**
- `Content-Type`: inferred from file extension (`text/markdown`, `text/plain`, `application/typescript`, etc.)
- Body: raw file content.

**Behavior:**
1. Look up `artifact_versions` row by `artifact_id` + `version_number`.
2. Verify `file_path` exists in `file_manifest`.
3. Fetch from S3: `{s3_prefix}{file_path}`.
4. Stream to client.

**Errors:**
- `404` if version or file not found.

---

### `POST /api/artifacts/{id}/iterate`

Submit contextual feedback to trigger a targeted iteration.

**Request:**
```json
{
  "file_path": "report.md",
  "highlighted_text": "The pricing comparison shows Notion at $10/user/month.",
  "highlight_start": 1420,
  "highlight_end": 1480,
  "instruction": "Add per-seat vs. flat-rate pricing breakdown for all three competitors."
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file_path` | `string` | No | Which file. Null = whole artifact (single-file prose). |
| `highlighted_text` | `string` | No | The verbatim highlighted text. |
| `highlight_start` | `integer` | No | Character offset. |
| `highlight_end` | `integer` | No | Character offset. |
| `instruction` | `string` | Yes | The user's change request. |

**Response: `202 Accepted`**
```json
{
  "comment_id": "uuid",
  "execution_wave_id": "uuid",
  "artifact_status": "drafting",
  "message": "Iteration started."
}
```

**Behavior:**
1. Creates `contextual_comment` row linked to the current version.
2. Creates `execution_wave` row with `trigger = 'iteration'`, `trigger_comment_id`.
3. Sets `artifact.status = 'drafting'`.
4. Enqueues `execute_artifact_dag` with the iteration prompt (TDD-03 Section 4.5).

**Errors:**
- `400` if artifact is not in `in_review` status.
- `429` if per-artifact or monthly budget exceeded.

---

### `PATCH /api/artifacts/{id}/approve`

Approve a prose artifact. (Code artifacts are approved via PR merge webhook.)

**Response: `200 OK`**
```json
{
  "id": "uuid",
  "status": "approved",
  "approved_at": "2026-03-26T11:00:00Z"
}
```

**Behavior:**
1. Sets `artifact.status = 'approved'`, `artifact.approved_at = now()`.
2. Checks reflection trigger conditions for all agents involved (TDD-03 Section 9.1).
3. Enqueues reflection Celery tasks if thresholds met.

**Errors:**
- `400` if artifact is not in `in_review` status.

---

### `PATCH /api/artifacts/{id}/cancel`

Cancel an artifact (soft archive).

**Response: `200 OK`**
```json
{
  "id": "uuid",
  "status": "cancelled",
  "cancelled_at": "2026-03-26T11:00:00Z"
}
```

**Behavior:**
1. If `status == 'drafting'`: revoke the active Celery task (if any), set wave status to `cancelled`.
2. Sets `artifact.status = 'cancelled'`, `artifact.cancelled_at = now()`.

**Errors:**
- `400` if artifact is already `approved` or `cancelled`.

---

### `GET /api/projects/{project_id}/artifacts`

List all artifacts in a project.

**Query params:** `limit`, `cursor`, `status` (optional filter: `drafting`, `in_review`, `approved`, `cancelled`).

**Response: `200 OK`** — Same paginated format as other list endpoints, with artifact summary objects.

---

## 6. Sufficiency Check

### `POST /api/briefs/sufficiency-check`

Standalone sufficiency check (can be called before artifact creation or on an existing artifact).

**Request:**
```json
{
  "artifact_type": "prose",
  "title": "Competitive Analysis",
  "goal": "...",
  "target_audience": "...",
  "context": "...",
  "description": "Write a competitive analysis of SaaS."
}
```

**Response: `200 OK`** — Same schema as `POST /api/artifacts/{id}/validate` (see Section 5).

This endpoint does NOT require an artifact to exist — it's a pure validation call. The frontend can call it from the brief form before saving.

---

## 7. Documents

### `GET /api/projects/{project_id}/documents`

List documents uploaded to a project.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "filename": "competitor-report.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 2458000,
      "chunk_count": 42,
      "processing_status": "ready",
      "created_at": "2026-03-20T10:00:00Z"
    }
  ]
}
```

---

### `POST /api/projects/{project_id}/documents`

Upload a document. Multipart form upload.

**Request:** `Content-Type: multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `binary` | Yes | The file (PDF, DOCX, TXT, MD, CSV, JSON, YAML). Max 20 MB. |

**Response: `201 Created`**
```json
{
  "id": "uuid",
  "filename": "competitor-report.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 2458000,
  "processing_status": "pending"
}
```

**Behavior:**
1. Validate file type and size (max 20 MB).
2. Upload to S3: `documents/{document_id}/{filename}`.
3. Create `documents` row with `processing_status = 'pending'`.
4. Enqueue `process_document_upload` Celery task (chunking + embedding).

---

### `DELETE /api/projects/{project_id}/documents/{document_id}`

Delete a document and its embeddings.

**Response: `204 No Content`**

**Behavior:**
1. Delete `document_chunks` rows (cascade).
2. Delete S3 object.
3. Delete `documents` row.

---

## 8. Git Provider Connections

### `GET /api/git-providers/connections`

List all Git provider connections for the workspace.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "provider": "github",
      "display_name": "My GitHub",
      "status": "active",
      "repositories": [
        { "owner": "acme", "name": "webapp", "default_branch": "main", "webhook_configured": true }
      ],
      "last_verified_at": "2026-03-25T10:00:00Z",
      "created_at": "2026-03-01T10:00:00Z"
    }
  ]
}
```

---

### `POST /api/git-providers/connections`

Create a new Git provider connection using a PAT (AD-14).

**Request:**
```json
{
  "provider": "github",
  "display_name": "My GitHub",
  "access_token": "ghp_xxxxxxxxxxxxxxxxxxxx"
}
```

**Response: `201 Created`** — Returns the connection object (without `access_token`).

**Behavior:**
1. Validate the token by calling the GitHub/GitLab API (list user + repos).
2. Encrypt the token and store in `access_token_encrypted`.
3. Store discovered repositories in the `repositories` JSONB.
4. Set `status = 'active'`.

**Errors:**
- `400` if the token is invalid or has insufficient permissions.

---

### `POST /api/git-providers/connections/{id}/test`

Test a Git provider connection.

**Response: `200 OK`**
```json
{
  "ok": true,
  "user": "octocat",
  "scopes": ["repo", "admin:repo_hook"],
  "rate_limit_remaining": 4950
}
```

---

### `GET /api/git-providers/connections/{id}/repos`

List repositories accessible via this connection.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "owner": "acme",
      "name": "webapp",
      "full_name": "acme/webapp",
      "default_branch": "main",
      "private": true,
      "webhook_configured": true
    }
  ]
}
```

---

### `POST /api/git-providers/connections/{id}/repos/{owner}/{repo}/webhook`

Configure (or reconfigure) the webhook on a specific repository. Auto-registers the webhook via the GitHub/GitLab API (AD-17).

**Response: `200 OK`**
```json
{
  "webhook_id": 12345,
  "webhook_url": "https://your-domain.com/api/webhooks/github",
  "events": ["pull_request", "pull_request_review_comment", "pull_request_review"],
  "status": "active"
}
```

**Behavior:**
1. Generate a random `webhook_secret` and store on the connection row.
2. Call `POST /repos/{owner}/{repo}/hooks` (GitHub API) with:
   - `url`: The backend's webhook endpoint.
   - `secret`: The generated secret.
   - `events`: `["pull_request", "pull_request_review_comment", "pull_request_review"]`.
3. Mark the repo as `webhook_configured = true` in the connection's `repositories` JSONB.

**Required PAT scope:** `admin:repo_hook`.

**Errors:**
- `400` if the PAT lacks the `admin:repo_hook` scope.
- `409` if webhook already exists for this repo (idempotent — update instead of fail).

---

### `DELETE /api/git-providers/connections/{id}`

Delete a Git provider connection. Removes all configured webhooks first.

**Response: `204 No Content`**

**Behavior:**
1. For each repo with `webhook_configured = true`: call `DELETE /repos/{owner}/{repo}/hooks/{webhook_id}` (best-effort — don't fail if webhook already removed).
2. Delete the connection row.

---

## 9. GitHub/GitLab Integration Flow

### 9.1 Push Flow (Code Artifact Execution Completion)

Executed at the end of `execute_artifact_dag` when `artifact.artifact_type == "code"`:

```
1. Load git_provider_connection for the workspace
2. Determine target repo from artifact.git_repo_url
3. Find matching connection + repo in git_provider_connections.repositories
4. Get authenticated clone URL: https://x-access-token:{token}@github.com/{owner}/{repo}.git
5. Clone the base branch (sparse checkout)
6. Create feature branch: artifact/{artifact_id_short}  (e.g., artifact/a1b2c3d4)
7. Write artifact files from ArtifactVersion.file_manifest to the working tree
8. Commit: "[AI Agent Team] {artifact.title}"
9. Push feature branch to remote
10. Create PR via GitHub API:
    POST /repos/{owner}/{repo}/pulls
    {
      "title": "{artifact.title}",
      "body": "## AI Agent Team Deliverable\n\n**Goal:** {artifact.goal}\n\n**Assumptions:**\n{assumptions list}\n\n**Sources:**\n{sources list}\n\n---\n🤖 Generated by [AI Agent Team](app-url) — [View in app](artifact-url)",
      "head": "artifact/{artifact_id_short}",
      "base": "{artifact.git_base_branch}"
    }
11. Store PR URL and number: artifact.git_pr_url, artifact.git_pr_number, artifact.git_feature_branch
```

### 9.2 Iteration Push (Updated Commits)

When an iteration completes for a code artifact that already has a PR:

```
1. Checkout the existing feature branch
2. Overwrite changed files from the new ArtifactVersion
3. Commit: "[AI Agent Team] Iteration v{version} — {comment.instruction[:80]}"
4. Push to the same branch
5. The PR updates automatically (GitHub shows the new commit)
```

No new PR is created — commits are added to the existing branch.

### 9.3 Webhook Events

See Section 10 (Webhooks) for the full webhook handling spec.

---

## 10. Webhooks

### `POST /api/webhooks/github`

Receives webhook events from GitHub.

**Security:**
- Validates `X-Hub-Signature-256` header against the stored `webhook_secret`.
- Rejects events with invalid signatures (returns `401`).
- Rejects events for unknown PRs (returns `200` with no action — don't leak information).

### `POST /api/webhooks/gitlab`

Receives webhook events from GitLab.

**Security:**
- Validates `X-Gitlab-Token` header against the stored `webhook_secret`.
- Same rejection logic as GitHub.

### 10.1 Events Handled

#### `pull_request_review_comment` (GitHub) / `note` on MR (GitLab)

**Trigger:** Someone leaves an inline comment on the PR.

**Behavior:**
1. Extract PR number from payload.
2. Find matching artifact via `artifacts.git_pr_number`.
3. If not found → log and return `200` (ignore).
4. Check `contextual_comments.external_comment_id` for dedup → if exists, return `200`.
5. Create `contextual_comment` row:
   - `source = 'github_pr'` or `'gitlab_mr'`
   - `external_comment_id = payload.comment.id`
   - `file_path = payload.comment.path` (inline comment location)
   - `instruction = payload.comment.body`
   - `highlight_start/end` from diff hunk position (best-effort mapping)
6. Create `execution_wave` row with `trigger = 'iteration'`, `trigger_comment_id`.
7. Set `artifact.status = 'drafting'`.
8. Enqueue `execute_artifact_dag`.

**Response: `200 OK`** (always — webhook endpoints should not return errors to GitHub).

#### `pull_request_review` (GitHub)

**Trigger:** Someone submits a PR review with `state = 'changes_requested'`.

**Behavior:** If the review body is non-empty, treat it like a review comment (same flow as above but `instruction = review.body`, no file-specific location).

#### `pull_request` with `action = 'closed'` and `merged = true`

**Trigger:** The PR is merged.

**Behavior:**
1. Find matching artifact.
2. Set `artifact.status = 'approved'`, `artifact.approved_at = now()`.
3. Check reflection trigger conditions.

#### `pull_request` with `action = 'closed'` and `merged = false`

**Trigger:** The PR is closed without merging.

**Behavior:** No automatic action. The artifact stays in `in_review`. The user can cancel it manually in the app if desired.

### 10.2 Webhook Retry & Fallback

GitHub retries webhook delivery if it receives a non-2xx response. Our endpoint always returns `200` after processing (even if internal processing fails — we log errors instead of returning them).

**Fallback polling:** If webhooks are not configured for a repo (user skipped webhook setup), the backend has NO automatic fallback in MVP. The user must submit iteration feedback through the in-app review screen. Webhook setup is strongly encouraged during connection setup.

---

## 11. MCP Connections

### `GET /api/mcp/connections`

List all MCP connections for the workspace.

**Response: `200 OK`**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Notion",
      "server_url": "https://mcp.notion.so/v1",
      "auth_type": "api_key",
      "status": "active",
      "discovered_tools": [
        {
          "name": "read_page",
          "description": "Read a Notion page by ID",
          "input_schema": { "type": "object", "properties": { "page_id": { "type": "string" } } }
        },
        {
          "name": "search",
          "description": "Search Notion pages",
          "input_schema": { "type": "object", "properties": { "query": { "type": "string" } } }
        }
      ],
      "last_verified_at": "2026-03-25T10:00:00Z",
      "created_at": "2026-03-10T10:00:00Z"
    }
  ]
}
```

---

### `POST /api/mcp/connections`

Create a new MCP connection.

**Request:**
```json
{
  "name": "Notion",
  "server_url": "https://mcp.notion.so/v1",
  "auth_type": "api_key",
  "auth_config": {
    "api_key": "ntn_xxxxxxxxxxxx"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Display name |
| `server_url` | `string` | Yes | MCP server endpoint |
| `auth_type` | `string` | Yes | `"api_key"`, `"oauth"`, or `"none"` |
| `auth_config` | `object` | Depends | Auth credentials (encrypted at rest) |

**Response: `201 Created`** — Returns connection object (without `auth_config`).

**Behavior:**
1. Encrypt `auth_config` and store.
2. Attempt tool discovery (see below).
3. If discovery succeeds, populate `discovered_tools` and set `status = 'active'`.
4. If discovery fails, set `status = 'error'`.

---

### `POST /api/mcp/connections/{id}/test`

Test an MCP connection by pinging the server and re-discovering tools.

**Response: `200 OK`**
```json
{
  "ok": true,
  "server_version": "1.0.0",
  "tools_count": 5,
  "latency_ms": 120
}
```

---

### `POST /api/mcp/connections/{id}/discover-tools`

Re-discover available tools on the MCP server.

**Response: `200 OK`**
```json
{
  "tools": [
    {
      "name": "read_page",
      "description": "Read a Notion page by ID",
      "input_schema": { ... }
    }
  ]
}
```

**Behavior:** Calls the MCP server's `tools/list` method. Stores the result in `discovered_tools` JSONB.

---

### `DELETE /api/mcp/connections/{id}`

Delete an MCP connection.

**Response: `204 No Content`**

---

### 11.1 How MCP Tools Reach Agents

MCP connections are bound at the **workspace level** (not per-agent, not per-project). During execution:

1. The orchestrator loads all `mcp_connections` where `status = 'active'` for the workspace.
2. For each connection, each discovered tool becomes an Anthropic `tool_use` definition:
   - `name`: `mcp_{connection_name}_{tool_name}` (namespaced to avoid collisions).
   - `description`: from `discovered_tools[].description`.
   - `input_schema`: from `discovered_tools[].input_schema`.
3. When the agent calls an MCP tool, the executor proxies the request to the MCP server with the stored auth credentials.
4. Timeout: 30 seconds per MCP tool call.

---

## 12. Usage & Cost Tracking

### `GET /api/usage`

Get usage statistics for the workspace.

**Query params:** `period` (optional: `"day"`, `"week"`, `"month"` — default `"month"`).

**Response: `200 OK`**
```json
{
  "period": "month",
  "period_start": "2026-03-01T00:00:00Z",
  "total_cost_usd": 42.50,
  "total_input_tokens": 1250000,
  "total_output_tokens": 380000,
  "budget": {
    "monthly_limit_usd": 50.00,
    "monthly_spent_usd": 42.50,
    "remaining_usd": 7.50,
    "usage_pct": 85
  },
  "by_model": {
    "sonnet": { "cost_usd": 38.00, "input_tokens": 1100000, "output_tokens": 340000 },
    "opus": { "cost_usd": 4.50, "input_tokens": 150000, "output_tokens": 40000 }
  },
  "by_artifact": [
    {
      "artifact_id": "uuid",
      "title": "Q3 Competitive Analysis",
      "cost_usd": 0.65,
      "versions": 2
    }
  ],
  "daily_breakdown": [
    { "date": "2026-03-26", "cost_usd": 2.10, "artifact_count": 3 },
    { "date": "2026-03-25", "cost_usd": 1.80, "artifact_count": 2 }
  ]
}
```

**Computed from:** `execution_waves` (cost, tokens), `artifact_versions` (per-artifact breakdown), `workspaces` (budget info).

---

### `PATCH /api/usage/budget`

Update the monthly budget ceiling.

**Request:**
```json
{
  "monthly_budget_usd": 100.00
}
```

**Response: `200 OK`**
```json
{
  "monthly_budget_usd": 100.00,
  "monthly_spent_usd": 42.50,
  "remaining_usd": 57.50
}
```

---

## 13. Health

### `GET /health`

**Response: `200 OK`**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "services": {
    "database": "ok",
    "redis": "ok",
    "s3": "ok"
  }
}
```

Checks: PostgreSQL connection, Redis ping, MinIO bucket exists. Returns `503` if any service is down.

---

## 14. Endpoint Summary

### Core Artifact Flow

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/artifacts` | Create artifact from brief |
| `POST` | `/api/artifacts/{id}/validate` | Run sufficiency check |
| `POST` | `/api/artifacts/{id}/delegate` | Route + execute (preview or confirm) |
| `GET` | `/api/artifacts/{id}` | Get artifact detail |
| `GET` | `/api/artifacts/{id}/status` | Heartbeat polling |
| `GET` | `/api/artifacts/{id}/versions` | List versions |
| `GET` | `/api/artifacts/{id}/versions/{v}/files/{path}` | Download file |
| `POST` | `/api/artifacts/{id}/iterate` | Submit feedback + trigger iteration |
| `PATCH` | `/api/artifacts/{id}/approve` | Approve (prose) |
| `PATCH` | `/api/artifacts/{id}/cancel` | Cancel (soft archive) |
| `POST` | `/api/briefs/sufficiency-check` | Standalone brief validation |
| `GET` | `/api/projects/{pid}/artifacts` | List project artifacts |

### Roster & Agents

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/onboarding` | First-time setup |
| `GET` | `/api/roster` | List agents |
| `GET` | `/api/roster/{id}` | Get agent detail |
| `POST` | `/api/roster` | Add agent |
| `PATCH` | `/api/roster/{id}` | Update agent |
| `DELETE` | `/api/roster/{id}` | Archive agent |
| `DELETE` | `/api/roster/{id}/permanent` | Hard delete agent |
| `GET` | `/api/roster/{id}/skills` | List skills |
| `GET` | `/api/roster/{id}/learning-profile` | Learning profile |
| `POST` | `/api/roster/{id}/research` | Trigger research |
| `POST` | `/api/roster/{id}/reflect` | Trigger reflection |
| `POST` | `/api/roster/{id}/knowledge` | Upload doc/URL to agent knowledge |
| `GET` | `/api/roster/{id}/knowledge-recommendations` | List knowledge gaps |
| `POST` | `/api/roster/{id}/knowledge-recommendations/{rid}/apply` | Apply recommendation |
| `POST` | `/api/roster/{id}/knowledge-recommendations/{rid}/dismiss` | Dismiss recommendation |
| `GET` | `/api/roster/readiness/global` | Global readiness summary |

### Projects & Documents

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List projects |
| `POST` | `/api/projects` | Create project |
| `PATCH` | `/api/projects/{id}` | Update project |
| `DELETE` | `/api/projects/{id}` | Delete project |
| `GET` | `/api/projects/{id}/context` | Get brief state |
| `PUT` | `/api/projects/{id}/context/draft` | Save brief draft |
| `POST` | `/api/projects/{id}/context/publish` | Publish brief |
| `GET` | `/api/projects/{pid}/documents` | List documents |
| `POST` | `/api/projects/{pid}/documents` | Upload document |
| `DELETE` | `/api/projects/{pid}/documents/{did}` | Delete document |

### Integrations

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/git-providers/connections` | List Git connections |
| `POST` | `/api/git-providers/connections` | Create Git connection (PAT) |
| `POST` | `/api/git-providers/connections/{id}/test` | Test connection |
| `GET` | `/api/git-providers/connections/{id}/repos` | List repos |
| `POST` | `/api/git-providers/connections/{id}/repos/{o}/{r}/webhook` | Configure webhook |
| `DELETE` | `/api/git-providers/connections/{id}` | Delete connection |
| `GET` | `/api/mcp/connections` | List MCP connections |
| `POST` | `/api/mcp/connections` | Create MCP connection |
| `POST` | `/api/mcp/connections/{id}/test` | Test connection |
| `POST` | `/api/mcp/connections/{id}/discover-tools` | Discover tools |
| `DELETE` | `/api/mcp/connections/{id}` | Delete connection |

### Webhooks

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/webhooks/github` | GitHub webhook receiver |
| `POST` | `/api/webhooks/gitlab` | GitLab webhook receiver |

### Usage & System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/usage` | Usage stats |
| `PATCH` | `/api/usage/budget` | Update budget ceiling |
| `GET` | `/health` | Health check |

**Total: 44 endpoints.**

---

## 15. Verification Checklist

- [ ] All 39 endpoints return correct HTTP status codes and response schemas
- [ ] Cursor-based pagination works: first page (no cursor), subsequent pages (with cursor), empty page (`has_more: false`)
- [ ] `POST /api/onboarding` creates workspace + agents and enqueues learning tasks
- [ ] `POST /api/artifacts/{id}/delegate` with `confirm: false` returns plan preview; with `confirm: true` enqueues execution
- [ ] `GET /api/artifacts/{id}/status` returns heartbeat data during execution and `null` otherwise
- [ ] `GET /api/artifacts/{id}/versions/{v}/files/{path}` proxies file content from S3 with correct Content-Type
- [ ] `POST /api/artifacts/{id}/iterate` creates comment + wave and enqueues execution
- [ ] `POST /api/git-providers/connections` validates the PAT against GitHub/GitLab API before storing
- [ ] `POST /api/git-providers/connections/{id}/repos/{o}/{r}/webhook` registers a webhook on GitHub with correct events and secret
- [ ] `POST /api/webhooks/github` validates signature, deduplicates via `external_comment_id`, triggers iteration for PR comments, and approves on merge
- [ ] `POST /api/mcp/connections` discovers tools and stores them in `discovered_tools` JSONB
- [ ] `GET /api/usage` computes aggregates from `execution_waves` and `artifact_versions` correctly
- [ ] Error responses follow the `{ "error": { "code", "message", "details" } }` format
- [ ] `DELETE /api/projects/{id}` requires `X-Confirm-Delete: true` header
- [ ] `POST /api/roster/{id}/knowledge` accepts file upload or URL and triggers ingestion
- [ ] `GET /api/roster/{id}/knowledge-recommendations` returns actionable gap analysis
- [ ] `GET /api/roster/readiness/global` aggregates readiness across all active agents
