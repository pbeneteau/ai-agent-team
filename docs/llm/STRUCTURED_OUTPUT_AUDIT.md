# Structured Output Audit

## Scope

This document maps every known LLM flow that can produce machine-readable output or pseudo-structured text, plus the main failure modes, fallbacks, and current hardening status.

## Runtime Baseline

Primary runtime:
- `backend/app/core/structured_json.py`

Telemetry now captured at runtime:
- `generation_channel`
- `parse_failed`
- `validation_failed`
- `provider_error`
- `stop_reason`
- `prompt_length`
- `schema_length`
- `raw_text_length`
- `empty_response`
- retry / repair flags

Core rule:
- Prefer native structured generation or tool calls whenever the backend needs machine-readable data.
- Keep visible prose separate from machine payloads.
- Keep prompts and schemas minimal. Ask for the smallest usable result, not a narrative explanation.

## Flow Matrix

| Flow | Files | Mode | Fallback | Main risk | Current status |
| --- | --- | --- | --- | --- | --- |
| `task_planner` | `backend/app/core/orchestrator.py` | `text_json` + repair | backend default plan | parse drift, truncation, over-long brief | instrumented |
| `task_result_metadata` | `backend/app/core/orchestrator.py` | `text_json` + repair | local metadata parsing | partial JSON, free-form drift | instrumented |
| `learn_from_work` | `backend/app/core/learning.py` | `text_json` + repair | skip memory update | noisy output, weak selectivity | instrumented |
| `knowledge_audit` | `backend/app/core/knowledge.py` | `native_json_schema` | heuristic audit | oversized prompt, validation drift, truncation | hardened |
| `teams_recommendations` | `backend/app/api/routes/teams.py` | `native_json_schema` | heuristic recommendations | oversized schema, verbose staffing payload | tightened |
| `associate` action extraction | `backend/app/agents/associate.py`, `backend/app/models/chat_actions.py` | `tool_use`, then `legacy_json`, then `text_only` | visible text only | invalid tool payload silently counted as success | hardened |
| `team_builder_proposal` | `backend/app/core/team_builder.py` | `legacy_json` extracted from mixed response | none | prose + JSON mixed output | reduced verbosity |
| `project_briefing` | `backend/app/core/learning.py` | free-form markdown | none | large batch response per team | migrated to per-agent generation |
| `targeted_rebriefing` | `backend/app/core/learning.py` | free-form markdown | none | long role context rewrite | tightened |
| `document_rebriefing` | `backend/app/core/learning.py` | free-form markdown | none | giant batch response for all agents | migrated to per-agent generation |

## Highest-Risk Areas

### 1. Native structured flows with large contracts

Files:
- `backend/app/core/knowledge.py`
- `backend/app/api/routes/teams.py`
- `backend/app/models/team_recommendations.py`

Risk pattern:
- prompt injects too much context
- schema asks for too many free-text fields
- model returns correct semantics but invalid or truncated structure

Mitigations already applied:
- smaller prompt budgets
- tighter field-level length constraints
- shorter evidence / rationale expectations
- section-budgeted prompt construction
- targeted native truncation salvage before heuristic fallback

### 2. Interactive chat actions

Files:
- `backend/app/agents/associate.py`
- `backend/app/models/chat_actions.py`
- `backend/app/models/plan.py`

Risk pattern:
- tool call fails validation
- legacy JSON fallback succeeds or fails
- flow was previously logged as success even after structured degradation

Mitigations already applied:
- explicit action-resolution path
- degraded channels such as `tool_use_invalid_text_only`
- minimal tool schema constraints
- shorter visible-response rules

### 3. Legacy mixed prose + machine payload

Files:
- `backend/app/core/team_builder.py`

Risk pattern:
- visible response and machine payload share the same text output
- JSON extraction depends on the assistant following formatting instructions exactly

Mitigations already applied:
- shorter prose rule
- smaller token budget
- failure now tracked by the shared parser runtime

### 4. Batch markdown generation

Files:
- `backend/app/core/learning.py`

Risk pattern:
- one response used to carry multiple agents' outputs
- parsing depends on markers and complete delivery
- token budgets were far larger than needed

Mitigations already applied:
- per-agent generation for project briefing
- per-agent generation for document rebriefing
- shared prompt builder for role-scoped project context

## Prompt / Schema Reduction Principles

Apply these principles to any future flow:
- keep only fields that drive execution, validation, or UI decisions
- cap each free-text field explicitly
- prefer IDs, labels, and short reasons over long excerpts
- avoid duplicate fields such as `summary` plus `reason` plus `description` unless each is consumed differently
- split large generation into staged flows when the second stage depends on user validation
- prefer one structured action plus one short visible message over a blended answer

## Token Budget Recalibration

Applied reductions in this pass:

| Flow | Previous | Current | Rationale |
| --- | --- | --- | --- |
| `knowledge_audit` | `1400` | `1200` | tighter schema, shorter recommendation payload, and extra output margin for reliability |
| `teams_recommendations` | `2200` | `1600` | schema now caps string sizes and team staffing breadth |
| `associate` chat stream | `2048` | `1600` | tighter visible-text policy and smaller tool payloads |
| `team_builder` | `2048` | `1400` | legacy mixed output kept intentionally short |
| role project-context generation | `2048` or `4096` batch | `1400` per agent | per-agent generation removes oversized batch responses |

Budget policy:
- start with the smallest budget compatible with the reduced schema
- scale only from observed failures, not from hypothetical verbosity
- prefer splitting a flow over inflating `max_tokens`

## Audit Checklist For New Flows

Before adding a new structured-output flow:
- define whether the source of truth is `tool_use`, `native_json_schema`, or text parsing
- define the exact fallback behavior and whether the product can tolerate it
- cap all free-text fields in the schema
- set an intentionally small `max_tokens` budget, then increase only if data shows it is necessary
- log `request_name`, `generation_channel`, success/failure, and stop reason
- add tests for parse failure, validation failure, empty response, and truncation-like output

## Open Follow-Ups

- migrate remaining `text_json` orchestration flows to native structured output where practical
- remove or fully replace the legacy `team_builder` path
- expose richer failure causes in any UI that displays structured-output observability
- add regression tests for degraded `associate` channels and per-agent briefing flows
