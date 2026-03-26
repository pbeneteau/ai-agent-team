# Phase 3 — AI & Agentic Engine Design (TDD)

> **Document type:** Technical Design Document
> **Status:** Draft
> **Source of truth:** `docs/VISION_2.0.md`, `docs/TDD/01_PRD_AND_WORKFLOWS.md`, `docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md`
> **Scope:** Prompt engineering, memory management, DAG orchestration logic, and tool-use architecture. No database schema (see TDD-02), no frontend, no API contracts.

---

## Architectural Decisions Log

| ID | Decision | Rationale |
|---|---|---|
| **AD-8** | Hybrid DAG generation: hardcoded templates + LLM router | Generating DAGs from scratch is slow and hallucination-prone. Predefined templates give speed and determinism; a fast LLM call routes briefs to the best template. |
| **AD-9** | One combined Haiku call for auto-assembly + routing | Speed is critical. One Haiku call reads the brief, selects a DAG template, AND maps roster agents to template slots. Single JSON response. |
| **AD-10** | Sufficiency check uses Sonnet | Manual "Validate" click means 2-4s latency is acceptable. Sonnet catches subtle ambiguities far better than Haiku. Cost justified by massive brief quality improvement. |
| **AD-11** | Full upstream output with 15k token cap (truncate middle) | Cross-functional handoffs need high fidelity (hex codes, spacing rules). Summarizing destroys technical detail. Token cap prevents runaway context. |
| **AD-12** | Knowledge readiness via heuristic formula (no LLM) | Fast, synchronous DB calculation. Has project brief? Has core skills? Completed onboarding? → readiness_score = 100. |
| **AD-13** | Compile step only for multi-output merges | Single-track DAGs use the final agent's output directly. Compilation only when parallel branches need merging. Avoids wasted tokens and voice degradation. |

---

## 1. The Sufficiency Check Engine

### 1.1 Purpose

The gatekeeper that ensures agents receive unambiguous specs. Runs when the user clicks **"Validate"** or **"Delegate"** — never on keystroke.

### 1.2 Model

**Claude Sonnet** (`claude-sonnet-4-5`). Target latency: < 4 seconds. Typical cost: ~$0.003-0.008 per check.

### 1.3 System Prompt

```
You are a Brief Quality Analyst. Your job is to evaluate whether a project brief
is clear and complete enough for a team of AI agents to execute WITHOUT asking
any follow-up questions.

You must identify:
1. MISSING CONSTRAINTS — critical information the brief does not provide
   (audience, market, timeline, tech stack, success criteria, scope boundaries)
2. AMBIGUOUS LANGUAGE — words like "some", "various", "good", "comprehensive",
   "appropriate", "etc." that leave execution open to interpretation
3. SCOPE CREEP INDICATORS — briefs that try to do too many things at once
   or mix unrelated deliverables
4. MISSING SUCCESS CRITERIA — no way to evaluate whether the output is correct

Rules:
- Be strict but fair. A brief does not need to be a novel — it needs to be
  unambiguous.
- Only flag issues that would genuinely cause an AI agent to produce the wrong
  output or guess incorrectly.
- Do NOT flag stylistic preferences or minor omissions that agents can safely
  assume.
- For each issue, quote the EXACT substring from the user's text that is
  problematic (this is used for inline highlighting in the UI).
- Provide an actionable suggestion for each issue — tell the user exactly what
  to add or change.
- Maximum 5 issues. Prioritize the most critical ones.
- Classify each issue as "critical" (blocks execution) or "warning" (advisory).

Respond with valid JSON only. No markdown fences, no explanation outside the JSON.
```

### 1.4 User Message

```
Evaluate this brief:

Title: {artifact.title}
Goal: {artifact.goal}
Target Audience: {artifact.target_audience}
Context: {artifact.context}
Description: {artifact.description}

Artifact Type: {artifact.artifact_type}  (prose or code)
```

If `artifact_type == "code"`, append:
```
Tech Stack Context: {workspace.tech_stack}
Target Repository: {artifact.git_repo_url or "Not specified"}
```

### 1.5 Response Schema

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
      "suggestion": "Which specific competitors? US or EU market? What dimensions (Pricing, UX, Features)?"
    },
    {
      "severity": "warning",
      "field": "description",
      "matched_text": "Make it comprehensive and detailed.",
      "issue": "Ambiguous scope — 'comprehensive' is undefined.",
      "suggestion": "Define 'comprehensive': How many pages? What sections? What data sources?"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `eligible` | `boolean` | `true` if no `critical` issues. `warning` issues do not block. |
| `score` | `integer` | 0-100 quality score. Informational — not used for blocking logic. |
| `issues` | `array` | Max 5 items. |
| `issues[].severity` | `string` | `critical` or `warning`. |
| `issues[].field` | `string` | Which brief field the issue relates to (`title`, `goal`, `target_audience`, `context`, `description`). |
| `issues[].matched_text` | `string` | Exact substring from the user's input. The frontend uses this for inline highlighting (string search, not character offsets — more resilient to minor formatting changes). |
| `issues[].issue` | `string` | What's wrong. |
| `issues[].suggestion` | `string` | Actionable fix. |

### 1.6 Parsing & Error Handling

```python
async def run_sufficiency_check(artifact: Artifact, workspace: Workspace) -> SufficiencyResult:
    response = await anthropic.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SUFFICIENCY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_sufficiency_user_msg(artifact, workspace)}],
    )

    try:
        result = json.loads(response.content[0].text)
        return SufficiencyResult(**result)
    except (json.JSONDecodeError, ValidationError):
        # If LLM returns malformed JSON, fail open — allow submission with a warning
        return SufficiencyResult(eligible=True, score=50, issues=[{
            "severity": "warning",
            "field": "description",
            "matched_text": "",
            "issue": "Brief validation returned an unexpected result. Proceeding with caution.",
            "suggestion": "Consider reviewing your brief for clarity before delegating."
        }])
```

**Fail-open policy:** If the sufficiency check LLM call fails (timeout, malformed response), we do NOT block the user. We return `eligible: true` with a warning. The pre-flight check is a quality gate, not a security gate.

---

## 2. DAG Template Library

### 2.1 Concept

DAG templates are predefined, hardcoded execution plans. Each template defines:
- A sequence of **waves** (sequential stages)
- **Slots** within each wave (agent roles to be filled from the roster)
- **Dependencies** (which slots receive upstream output)
- Whether a **compile step** is needed (only for multi-output merges)

Templates are Python dataclasses, not database rows. Adding a new template = adding a Python file + registering it.

### 2.2 Template Schema

```python
@dataclass
class DagSlot:
    """A role in the DAG that will be filled by a roster agent."""
    slot_id: str                    # Unique key (e.g., "product_spec")
    label: str                      # Human-readable (e.g., "Product Specification")
    role_prompt: str                # Instructions for this agent in this DAG
    suggested_specializations: list[str]  # Roster matching hints (e.g., ["Product Expert", "Product Manager"])

@dataclass
class DagWave:
    """A parallel execution stage."""
    wave_number: int
    label: str                      # Heartbeat UI label (e.g., "Researching competitors...")
    slots: list[DagSlot]            # Agents to run in parallel
    depends_on: list[str]           # slot_ids from previous waves whose output this wave receives

@dataclass
class DagTemplate:
    """A predefined execution plan."""
    template_id: str                # Unique key (e.g., "code_feature")
    name: str                       # Human-readable (e.g., "Code Feature Build")
    description: str                # For the router LLM to understand when to pick this template
    artifact_type: str              # "prose", "code", or "both"
    waves: list[DagWave]
    needs_compile: bool             # Whether to add a final compile wave
    compile_slot: DagSlot | None    # If needs_compile, the compiler agent slot
```

### 2.3 MVP Template Definitions

#### Template: `code_feature`

**"Build a feature with product, design, and QA input."**

```
Wave 1 — "Defining requirements & design specs"
  ├── slot: product_spec
  │   role: "Analyze the brief. Produce: user flows, functional requirements,
  │          acceptance criteria, edge cases. Output as structured markdown."
  │   suggested_specializations: ["Product Expert", "Product Manager"]
  │
  └── slot: design_spec
      role: "Analyze the brief. Produce: component hierarchy, spacing/layout rules,
             design tokens, accessibility requirements, responsive behavior.
             Output as structured markdown."
      suggested_specializations: ["Design Expert", "UX Designer"]

Wave 2 — "Implementing code" (depends_on: [product_spec, design_spec])
  └── slot: implementation
      role: "Implement the feature using the product requirements and design specs
             provided as upstream context. Follow the design tokens exactly.
             Satisfy all acceptance criteria. Output working code files."
      suggested_specializations: ["Frontend Dev", "Backend Dev", "Full-Stack Dev"]

Wave 3 — "Quality review" (depends_on: [product_spec, design_spec, implementation])
  └── slot: qa_review
      role: "Review the implementation against the product requirements and design
             specs. Check: acceptance criteria coverage, edge case handling,
             accessibility compliance, code quality. Output a QA report with
             pass/fail per criterion and any issues found."
      suggested_specializations: ["QA Engineer"]

needs_compile: false  (QA is the final wave — its output + the code files = the artifact)
```

#### Template: `content_research`

**"Research a topic and produce a written deliverable."**

```
Wave 1 — "Researching & gathering data"
  ├── slot: researcher
  │   role: "Perform web research on the topic defined in the brief. Gather data,
  │          statistics, competitor information, market trends. Cite all sources
  │          with URLs. Output a structured research brief."
  │   suggested_specializations: ["Research Analyst", "Data Analyst"]
  │
  └── slot: framework_designer
      role: "Define the analysis framework: what dimensions to compare, what
             structure the final document should follow, what questions it must
             answer. Output as a document outline with section headers and
             key questions per section."
      suggested_specializations: ["Product Expert", "Strategy Analyst"]

Wave 2 — "Drafting the deliverable" (depends_on: [researcher, framework_designer])
  └── slot: writer
      role: "Write the full deliverable using the research data and the analysis
             framework. Follow the framework structure exactly. Cite sources from
             the research. Make it comprehensive but concise."
      suggested_specializations: ["Content Writer", "Strategy Analyst", "Technical Writer"]

Wave 3 — "Editorial review" (depends_on: [writer])
  └── slot: editor
      role: "Review for clarity, consistency, factual accuracy, tone, and
             completeness. Flag any unsupported claims. Suggest specific
             improvements. Output the revised document."
      suggested_specializations: ["Content Writer", "QA Engineer"]

needs_compile: false
```

#### Template: `simple_prose`

**"Write a document (no research phase needed)."**

```
Wave 1 — "Writing the deliverable"
  └── slot: writer
      role: "Write the deliverable as described in the brief. Follow the goal,
             target audience, and constraints exactly. Output the complete document."
      suggested_specializations: ["Content Writer", "Technical Writer"]

Wave 2 — "Editorial review" (depends_on: [writer])
  └── slot: editor
      role: "Review for clarity, tone, structure, and completeness. Fix any issues
             directly — output the final, polished document."
      suggested_specializations: ["Content Writer", "QA Engineer"]

needs_compile: false
```

#### Template: `code_bugfix`

**"Fix a bug with product context and QA validation."**

```
Wave 1 — "Analyzing the bug"
  └── slot: analyst
      role: "Analyze the bug description. Define: root cause hypothesis,
             reproduction steps, fix criteria, regression risk.
             Output as structured markdown."
      suggested_specializations: ["Product Expert", "QA Engineer"]

Wave 2 — "Implementing the fix" (depends_on: [analyst])
  └── slot: fixer
      role: "Implement the fix based on the analysis. Address the root cause,
             not just the symptom. Ensure fix criteria are met.
             Output the changed code files."
      suggested_specializations: ["Frontend Dev", "Backend Dev", "Full-Stack Dev"]

Wave 3 — "Validating the fix" (depends_on: [analyst, fixer])
  └── slot: validator
      role: "Validate the fix against the criteria from the analysis.
             Check for regressions. Output a pass/fail report."
      suggested_specializations: ["QA Engineer"]

needs_compile: false
```

#### Template: `multi_research`

**"Multiple researchers work in parallel, then a compiler merges."**

```
Wave 1 — "Parallel research tracks"
  ├── slot: researcher_a
  │   role: "Research track A as defined in the brief. Focus on your assigned
  │          dimension. Cite all sources. Output structured findings."
  │   suggested_specializations: ["Research Analyst"]
  │
  └── slot: researcher_b
      role: "Research track B as defined in the brief. Focus on your assigned
             dimension. Cite all sources. Output structured findings."
      suggested_specializations: ["Research Analyst", "Data Analyst"]

Wave 2 — "Compiling & synthesizing" (depends_on: [researcher_a, researcher_b])
  └── slot: compiler
      role: "Merge the research from both tracks into a unified, coherent
             deliverable. Resolve any contradictions. Maintain all citations.
             Follow the brief's structure requirements."
      suggested_specializations: ["Strategy Analyst", "Content Writer"]

needs_compile: false  (the compiler IS the final wave)
```

### 2.4 Adding New Templates

New templates are added as Python modules in `app/agents/dag_templates/`. Each module exports a `DagTemplate` instance. A registry dict maps `template_id → DagTemplate`. The router LLM sees all registered templates.

---

## 3. Auto-Assembly & DAG Routing

### 3.1 The Router Call

A single **Haiku** call that reads the brief, selects the best DAG template, and maps roster agents to template slots.

**Model:** `claude-haiku-4-5-20251001`. Target latency: < 2 seconds.

### 3.2 System Prompt

```
You are a Project Router. Given a user's brief and their available AI agent roster,
your job is to:

1. Select the best execution template for this brief.
2. Assign the best-matching agent from the roster to each slot in the template.

Rules:
- Match agents to slots based on their specialization. Pick the agent whose
  specialization is closest to the slot's suggested_specializations.
- Every slot MUST be filled. If no agent closely matches a slot, assign the
  most general-purpose agent available.
- Never assign the same agent to two slots in the same wave (parallel conflict).
  An agent CAN appear in different waves (sequential is safe).
- If a slot has no good match at all, set agent_id to null — the system will
  use a generic agent with the slot's role_prompt as its specialization.

Respond with valid JSON only. No markdown, no explanation.
```

### 3.3 User Message

```
## Brief

Title: {artifact.title}
Type: {artifact.artifact_type}
Goal: {artifact.goal}
Target Audience: {artifact.target_audience}
Context: {artifact.context}
Description: {artifact.description}

## Available Templates

{for template in registry:}
### {template.template_id}: {template.name}
{template.description}
Type: {template.artifact_type}
Slots: {[slot.slot_id + " (" + slot.label + ")" for wave in template.waves for slot in wave.slots]}
{end for}

## Your Roster (agents available for assignment)

{for agent in active_roster:}
- id: {agent.id} | name: {agent.name} | specialization: {agent.specialization} | readiness: {agent.readiness_score} | progression: {agent.progression_level}
{end for}
```

### 3.4 Response Schema

```json
{
  "template_id": "code_feature",
  "reasoning": "Brief asks to build a settings page — this is a code feature requiring product specs, design specs, implementation, and QA.",
  "slot_assignments": {
    "product_spec": { "agent_id": "uuid-product-expert", "agent_name": "Product Expert" },
    "design_spec": { "agent_id": "uuid-design-expert", "agent_name": "Design Expert" },
    "implementation": { "agent_id": "uuid-frontend-dev", "agent_name": "Frontend Dev" },
    "qa_review": { "agent_id": "uuid-qa-engineer", "agent_name": "QA Engineer" }
  },
  "estimated_waves": 3,
  "estimated_cost_usd": 0.85
}
```

### 3.5 Post-Router Processing

After the router returns:

1. **Validate** the response: template exists, all slots filled, no parallel conflicts.
2. **Build the `dag_plan` JSONB** by hydrating the template with assigned agent IDs.
3. **Build `assembled_team`** — deduplicated list of agent IDs.
4. **Build `step_labels`** — from template wave labels.
5. **Filter out agents below readiness gate** (< 50). If a critical slot has an under-ready agent, surface a warning to the user but don't block.
6. **Return the plan to the user** for confirmation: *"This will be handled by: Product Expert, Design Expert, Frontend Dev, QA Engineer. Template: Code Feature Build. Estimated cost: ~$0.85."*
7. On user confirmation → create `execution_wave` row → enqueue `execute_artifact_dag` Celery task.

### 3.6 Cost Estimation

The router's `estimated_cost_usd` is a rough estimate based on:
```python
def estimate_cost(template: DagTemplate, model_tier: str = "sonnet") -> float:
    """Rough estimate: ~4K input + ~2K output per agent slot."""
    total_slots = sum(len(wave.slots) for wave in template.waves)
    per_slot_cost = {
        "sonnet": 0.042,   # (4000 * 0.003 + 2000 * 0.015) / 1000
        "opus":   0.210,   # (4000 * 0.015 + 2000 * 0.075) / 1000
    }
    return round(total_slots * per_slot_cost.get(model_tier, 0.042), 2)
```

This is shown to the user before confirmation. Actual cost is tracked precisely during execution.

---

## 4. Prompt Architecture

### 4.1 The Recency Bias Rule

**The single most important architectural rule in the system:**

> The Current Project Brief and the specific artifact task instructions are **always injected at the very end** of the prompt. This leverages LLM recency bias — the model weights recent tokens more heavily, ensuring the agent prioritizes the current task over past habits.

### 4.2 Full Prompt Structure (Per-Agent Execution Call)

The Anthropic Messages API takes a `system` string and a `messages` array. We use:

```
┌─────────────────────────────────────────────────────────────┐
│  SYSTEM MESSAGE                                              │
│                                                              │
│  1. ROLE & IDENTITY                                          │
│     "You are {agent.name}, a {agent.specialization}."        │
│     Agent-specific system instructions from agent.system_prompt│
│                                                              │
│  2. AUTO-ASSUME RULE                                         │
│     (See Section 7 — injected into every agent system prompt)│
│                                                              │
│  3. OUTPUT FORMAT RULES                                      │
│     Artifact type–specific formatting instructions            │
│     (See Section 4.4)                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  USER MESSAGE                                                │
│                                                              │
│  ── SECTION A: LONG-TERM MEMORY (oldest context) ──         │
│                                                              │
│  4. AGENT SKILLS                                             │
│     All `agent_skills` rows where category = 'skill'         │
│     Formatted as markdown sections                           │
│     Budget: up to 5,000-8,000 tokens (see Section 5)        │
│                                                              │
│  5. AGENT WORK LEARNINGS                                     │
│     All `agent_skills` rows where category = 'work_learning' │
│     Formatted as markdown sections                           │
│     (Included in the 5k-8k budget)                           │
│                                                              │
│  ── SECTION B: EXECUTION CONTEXT ──                          │
│                                                              │
│  6. UPSTREAM AGENT OUTPUTS (DAG context)                     │
│     For each dependency in this wave's depends_on:           │
│     "## Output from {upstream_agent_name}: {slot_label}\n"   │
│     {upstream_output — raw, capped at 15,000 tokens}         │
│     (See Section 8)                                          │
│                                                              │
│  ── SECTION C: CURRENT TASK (most recent — recency bias) ── │
│                                                              │
│  7. PROJECT BRIEF                                            │
│     "## Project Context\n{project.brief_published}"          │
│     (Only if the project has a published brief)              │
│                                                              │
│  8. ARTIFACT BRIEF                                           │
│     "## Your Assignment\n"                                   │
│     "Title: {artifact.title}\n"                              │
│     "Goal: {artifact.goal}\n"                                │
│     "Target Audience: {artifact.target_audience}\n"          │
│     "Context: {artifact.context}\n"                          │
│     "Description: {artifact.description}\n"                  │
│                                                              │
│  9. WAVE-SPECIFIC TASK INSTRUCTIONS                          │
│     "## Your Task in This Wave\n"                            │
│     "{slot.role_prompt}"                                     │
│     (The specific instructions from the DAG template slot)   │
│                                                              │
│  ── END ──                                                   │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Why This Order Matters

```
Position in prompt          │ Content                    │ LLM attention weight
────────────────────────────┼────────────────────────────┼─────────────────────
Top of system message       │ Role, rules, auto-assume   │ High (primacy bias)
Middle of user message      │ Skills, learnings           │ Moderate (can fade)
Late in user message        │ Upstream DAG outputs       │ High (approaching end)
VERY END of user message    │ Project brief + task       │ HIGHEST (recency bias)
```

An agent with 7,000 tokens of past learnings will still faithfully follow the current brief because the brief is positioned last. Without this rule, the agent might default to old patterns when the current brief asks for something different.

### 4.4 Output Format Rules (by artifact type and wave role)

Injected into the system message, Section 3:

**For prose artifact slots (writer, editor, compiler):**
```
OUTPUT RULES:
- Output the deliverable directly. No preamble ("Here is the..."), no
  meta-commentary ("I'll now write..."), no sign-offs.
- Use Markdown formatting.
- If you make an assumption, mark it inline: [ASSUMPTION: <what and why>]
- If you used a source, cite it inline: [Source: <URL or reference>]
```

**For code artifact slots (implementation, fixer):**
```
OUTPUT RULES:
- Output complete, working code files.
- Use the following format for each file:

--- FILE: {relative/path/to/file.ext} ---
{file content}
--- END FILE ---

- Do not output partial files or pseudocode.
- If you make an assumption, add a code comment: // [ASSUMPTION: <what and why>]
- Follow the project's tech stack and conventions from the brief context.
```

**For analysis/spec slots (product_spec, design_spec, analyst, researcher):**
```
OUTPUT RULES:
- Output structured Markdown.
- Use headers, bullet points, and tables for clarity.
- Your output will be consumed by downstream agents — be precise and specific.
  Avoid vague language. Provide exact values (hex codes, pixel values, API
  endpoints) rather than descriptions.
- If you make an assumption, mark it: [ASSUMPTION: <what and why>]
- If you used a source, cite it: [Source: <URL or reference>]
```

**For QA/review slots (qa_review, validator, editor):**
```
OUTPUT RULES:
- If your role is review/QA, output a structured review report AND the
  corrected deliverable.
- Use this format:

## Review Report
| Criterion | Status | Notes |
|---|---|---|
| ... | PASS/FAIL | ... |

## Issues Found
1. [Issue description + location + suggested fix]

## Corrected Output
{the fixed/improved deliverable}
```

### 4.5 Iteration Prompts

When a user submits a contextual comment (highlight + instruction), the iteration runs a focused agent. The prompt structure stays the same (Sections 1-9), but with these modifications:

**Section 6 (Upstream context)** is replaced with:
```
## Previous Version (v{n})
{full content of the previous artifact version — from S3}

## User Feedback
File: {comment.file_path or "entire document"}
Highlighted text: "{comment.highlighted_text}"
Instruction: "{comment.instruction}"
```

**Section 9 (Wave task)** becomes:
```
## Your Task
Address the user's feedback on the previous version. Modify ONLY the section
the user highlighted. Preserve everything else unchanged. Output the complete
updated deliverable (not just the changed section).

If the feedback contradicts a previous assumption you made, remove the assumption
tag and apply the user's correction.
```

---

## 5. High-Token Memory Management

### 5.1 The Identity Budget

Agent memory (skills + work learnings from `agent_skills` table) is capped at **8,000 tokens**. This is our moat — the deeper the memory, the better the output, the harder to switch.

| Category | Content | Budget Share |
|---|---|---|
| `skill` | Learned capabilities, preferences, domain knowledge | Up to 6,000 tokens |
| `work_learning` | Verified insights and cautions from past artifacts | Up to 2,000 tokens |
| **Total** | | **8,000 tokens max** |

`briefing` entries (project context) are NOT counted against this budget. They are ephemeral — replaced on each rebriefing — and injected separately in the prompt (Section C, position 7).

### 5.2 Token Counting

Token counts are pre-computed on write using a fast tokenizer (Anthropic's `anthropic.count_tokens()` or `tiktoken` as a proxy). Stored in `agent_skills.token_count`.

**Budget check on every skill write:**
```python
async def check_and_enforce_budget(agent_id: str, new_content: str, category: str):
    current_total = await db.scalar(
        select(func.sum(AgentSkill.token_count))
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
    )
    new_tokens = count_tokens(new_content)

    if (current_total or 0) + new_tokens > MEMORY_BUDGET_TOKENS:  # 8000
        await trigger_compaction(agent_id)
        # After compaction, re-check — if still over, reject the write
```

### 5.3 Compaction (Not Truncation)

When memory approaches the 8,000-token ceiling, the system runs a **compaction cycle** — an LLM call that merges, deduplicates, and distills skills into fewer, denser entries.

**Model:** Sonnet (quality matters for preserving important nuances).

**Compaction Prompt:**

```
System:
You are a Knowledge Compactor. Your job is to compress an AI agent's accumulated
skills and learnings into a tighter, higher-signal summary without losing
important information.

Rules:
- Merge entries that cover the same topic.
- Remove entries that contradict each other (keep the more recent one).
- Remove entries that are obvious or generic (e.g., "write clearly" — every
  agent should do this).
- Preserve specific, hard-won knowledge: user preferences, brand voice rules,
  domain-specific conventions, technical patterns, past corrections.
- The output must be strictly smaller than the input (target: 60-70% of
  original token count).
- Maintain the same markdown format (## headers, bullet points).
- Do NOT invent new knowledge. Only consolidate what exists.

User:
## Agent: {agent.name} ({agent.specialization})

## Current Skills ({current_skill_tokens} tokens)
{all skill entries concatenated}

## Current Work Learnings ({current_learning_tokens} tokens)
{all work_learning entries concatenated}

Compact these into a single skills document and a single work learnings document.
Target total: {target_tokens} tokens maximum.

Output format:
### COMPACTED SKILLS
{compacted skills content}

### COMPACTED WORK LEARNINGS
{compacted work learnings content}
```

**After compaction:**
1. Delete all existing `skill` and `work_learning` rows for the agent.
2. Insert two new rows (one `skill`, one `work_learning`) with the compacted content.
3. Recount tokens. If still over budget (shouldn't happen), hard-truncate the oldest `work_learning` entries.

### 5.4 Prompt Assembly: Loading Skills into Context

```python
async def load_agent_memory(agent_id: str) -> str:
    """Load all skills + work learnings, formatted for prompt injection."""
    skills = await db.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .where(AgentSkill.category.in_(["skill", "work_learning"]))
        .order_by(AgentSkill.category, AgentSkill.updated_at.desc())
    )

    sections = []
    for skill in skills:
        header = "## Skill" if skill.category == "skill" else "## Work Learning"
        sections.append(f"{header}: {skill.title}\n{skill.content}")

    return "\n\n".join(sections)
```

This assembled string is injected at **position 4-5** of the user message (Section A: Long-Term Memory).

---

## 6. Tool-Use Architecture

### 6.1 Anthropic Native Tool Use

All agent tools are exposed via Anthropic's native `tool_use` feature. Each tool is defined as a JSON Schema and paired with a Python executor.

### 6.2 Tool Availability by Phase

| Tool | Learning | Execution | Reflection |
|---|---|---|---|
| `web_search` | Yes | Yes | No |
| `web_browser` | Yes | Yes | No |
| `vector_search` | Yes | Yes | No |
| `file_read` | Yes | Yes | Yes |
| `file_write` | Yes | Yes | Yes |
| `mcp_call` | No | Yes | No |
| `git_clone` | No | Yes | No |
| `git_push` | No | Yes | No |

During execution, the orchestrator builds the tool list based on the phase:

```python
def get_tools_for_phase(phase: str, workspace_mcp: list, workspace_git: list) -> list[ToolSpec]:
    base = [file_read_tool, file_write_tool]
    if phase in ("learning", "execution"):
        base += [web_search_tool, web_browser_tool, vector_search_tool]
    if phase == "execution":
        base += [mcp_tool(conn) for conn in workspace_mcp]
        base += [git_clone_tool, git_push_tool] if workspace_git else []
    return base
```

### 6.3 Tool Definitions

#### `web_search`

```json
{
  "name": "web_search",
  "description": "Search the web for information. Returns a list of results with titles, URLs, and snippets.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "The search query" },
      "num_results": { "type": "integer", "default": 5, "maximum": 10 }
    },
    "required": ["query"]
  }
}
```

**Executor:** Calls Serper API. Returns formatted results (title, URL, snippet per result).

#### `web_browser`

```json
{
  "name": "web_browser",
  "description": "Fetch and read the content of a web page. Returns extracted text content (max 8000 characters).",
  "input_schema": {
    "type": "object",
    "properties": {
      "url": { "type": "string", "description": "The URL to fetch" }
    },
    "required": ["url"]
  }
}
```

**Executor:** HTTP GET, HTML-to-text extraction (BeautifulSoup), truncated to 8,000 chars.

#### `vector_search`

```json
{
  "name": "vector_search",
  "description": "Search uploaded project documents using semantic similarity. Returns the most relevant text chunks.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Natural language search query" },
      "top_k": { "type": "integer", "default": 5, "maximum": 15 }
    },
    "required": ["query"]
  }
}
```

**Executor:** Embeds the query, runs pgvector cosine similarity search on `document_chunks` for the current project. Returns chunks with filename and content.

#### `file_read` / `file_write`

Scoped to the agent's isolated execution scratchpad within the Celery task. NOT the persistent S3 workspace. Files written here are ephemeral and used for intermediate work within a single execution.

```json
{
  "name": "file_write",
  "description": "Write content to a file in your workspace. Use this to produce your output files.",
  "input_schema": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Relative file path (e.g., 'src/index.ts')" },
      "content": { "type": "string", "description": "File content" }
    },
    "required": ["path", "content"]
  }
}
```

**Executor:** Writes to an in-memory dict (`{path: content}`) within the orchestrator task. At the end of execution, these files become the artifact version's file bundle uploaded to S3.

#### `mcp_call`

Dynamically generated per MCP connection:

```json
{
  "name": "mcp_{connection_name}_{tool_name}",
  "description": "{tool description from discovered_tools}",
  "input_schema": "{tool input_schema from discovered_tools}"
}
```

**Executor:** Proxies the call to the MCP server. Timeout: 30 seconds.

### 6.4 Agent Execution Loop

Using Anthropic's native messages API with `tool_use`:

```python
async def run_agent(
    system_prompt: str,
    user_message: str,
    tools: list[ToolSpec],
    model: str,
    max_iterations: int = 15,
    max_tokens: int = 8192,
) -> AgentResult:
    messages = [{"role": "user", "content": user_message}]
    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(max_iterations):
        response = await anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=[t.to_anthropic() for t in tools],
        )
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        if response.stop_reason == "end_turn":
            # Agent is done — extract final text
            result_text = extract_text_blocks(response.content)
            return AgentResult(
                text=result_text,
                files=collect_written_files(),
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )

        if response.stop_reason == "tool_use":
            # Execute all tool calls, append results, continue loop
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool = find_tool(block.name, tools)
                    result = await tool.execute(block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    # Max iterations reached — return whatever we have
    raise AgentMaxIterationError(f"Agent did not complete in {max_iterations} iterations")
```

---

## 7. Auto-Assume Protocol

### 7.1 The Rule

Agents **never** pause for human input during execution. If they encounter ambiguity, they make the safest reasonable assumption, log it visibly, and continue.

### 7.2 Prompt Injection

Appended to **every** agent system prompt (Section 2 of the system message):

```
═══════════════════════════════════════════════════════════════
CRITICAL OPERATING RULE — AUTO-ASSUME

If you encounter missing information, ambiguity, or a situation where you would
normally ask for clarification:
1. Make the safest, most reasonable assumption.
2. Document it CLEARLY inline in your output:
   [ASSUMPTION: <what you assumed and why>]
3. Continue working. Finish the deliverable.

You are fully autonomous. You will NEVER receive a follow-up message.
There is no human in the loop during execution. The user will review your
output after you are done and can override any assumption at that point.

DO NOT:
- Output questions to the user
- Say "I would need to know..." or "Please clarify..."
- Leave sections blank or with placeholders like "TBD" (unless you genuinely
  cannot even assume — in which case, mark as [TBD: <what's needed>])
- Stop mid-work because of uncertainty

ALWAYS prefer completing the work with assumptions over leaving gaps.
═══════════════════════════════════════════════════════════════
```

### 7.3 Assumption Extraction

After each agent completes, the orchestrator extracts assumptions from the output text:

```python
import re

ASSUMPTION_PATTERN = re.compile(r'\[ASSUMPTION:\s*(.+?)\]', re.IGNORECASE)
TBD_PATTERN = re.compile(r'\[TBD:\s*(.+?)\]', re.IGNORECASE)

def extract_assumptions(text: str, agent_name: str) -> list[dict]:
    assumptions = []
    for match in ASSUMPTION_PATTERN.finditer(text):
        assumptions.append({"text": match.group(1).strip(), "agent": agent_name})
    for match in TBD_PATTERN.finditer(text):
        assumptions.append({"text": f"TBD — {match.group(1).strip()}", "agent": agent_name})
    return assumptions
```

These are stored in `artifact_versions.assumptions` JSONB and displayed in the review sidebar.

---

## 8. Upstream Context Flow (Cross-Functional Handoffs)

### 8.1 The Core Mechanism

After each wave completes, agent outputs are stored in an in-memory dict within the orchestrator Celery task:

```python
wave_outputs: dict[str, WaveOutput] = {}
# key = slot_id, value = WaveOutput(text, files, agent_name, slot_label)
```

When building the prompt for a downstream agent, the orchestrator injects upstream outputs:

```python
def build_upstream_context(wave: DagWave, wave_outputs: dict) -> str:
    sections = []
    for dep_slot_id in wave.depends_on:
        output = wave_outputs[dep_slot_id]
        header = f"## Upstream Output — {output.agent_name}: {output.slot_label}"
        content = truncate_middle(output.text, max_tokens=UPSTREAM_TOKEN_CAP)
        sections.append(f"{header}\n\n{content}")
    return "\n\n---\n\n".join(sections)
```

### 8.2 Token Cap & Truncation Strategy

**Cap:** 15,000 tokens per upstream dependency (AD-11).

**Truncation method: middle-out.** If an upstream output exceeds 15,000 tokens:
1. Keep the first 7,000 tokens (introduction, structure, key definitions).
2. Insert: `\n\n[... {N} tokens truncated for brevity ...]\n\n`
3. Keep the last 8,000 tokens (conclusions, specific details, most recent content).

**Why middle-out:** Beginnings contain structure and context. Endings contain conclusions and specific recommendations. The middle is most likely to contain verbose details that can be inferred.

```python
def truncate_middle(text: str, max_tokens: int = 15000) -> str:
    tokens = count_tokens(text)
    if tokens <= max_tokens:
        return text

    # Split into sentences for cleaner cuts
    sentences = split_sentences(text)

    head_budget = int(max_tokens * 0.47)   # ~7,000
    tail_budget = int(max_tokens * 0.53)   # ~8,000

    head = take_tokens_from_start(sentences, head_budget)
    tail = take_tokens_from_end(sentences, tail_budget)
    truncated = tokens - count_tokens(head) - count_tokens(tail)

    return f"{head}\n\n[... {truncated} tokens truncated for brevity ...]\n\n{tail}"
```

### 8.3 File Handoffs (Code Artifacts)

For code artifact DAGs, upstream agents may reference files they wrote. The downstream agent receives:
1. The upstream text output (specs, requirements) — injected in the prompt.
2. The upstream file list — if the upstream agent wrote files via `file_write`, they are listed as available context but NOT injected into the prompt (too large). The downstream agent can reference them by name.

The orchestrator merges all file outputs across waves. If two agents write to the same path, the later wave's version wins (downstream overrides upstream).

---

## 9. Reflection & Learning Engine

### 9.1 Trigger Conditions

Reflection runs after an artifact is approved, if any of these are true:
- Agent has completed ≥ 3 artifacts since last reflection.
- It has been ≥ 7 days since `agent.last_reflection_at`.

Checked in application code after the approval state transition. Not a cron job.

### 9.2 Reflection Prompt

**Model:** Sonnet (quality matters for extracting nuanced learnings).

```
System:
You are a Learning Extractor. Your job is to analyze an AI agent's recent work
and extract reusable insights that will improve future performance.

Rules:
- Extract SPECIFIC, actionable learnings — not generic platitudes.
- Good: "User prefers bullet-point recommendations over paragraph prose"
- Bad: "Write clearly and concisely"
- Focus on: user corrections, preferences revealed through feedback, domain
  knowledge gained, effective approaches, mistakes to avoid.
- Each learning should be 1-2 sentences maximum.
- Output valid JSON only.

User:
## Agent: {agent.name} ({agent.specialization})

## Artifacts Completed Since Last Reflection

{for artifact in recent_artifacts:}
### Artifact: {artifact.title}
**Brief:** {artifact.description}
**Final Version:** v{artifact.current_version}

**User Feedback (contextual comments):**
{for comment in artifact.comments:}
- Highlighted: "{comment.highlighted_text}"
  Instruction: "{comment.instruction}"
  Resolved in: v{comment.resolved_in_version}
{end for}

{end for}

## Current Skills (for deduplication — do not repeat what's already known)
{agent's current skill entries}

Extract new learnings from these artifacts. Only include insights that are NOT
already captured in the current skills.
```

### 9.3 Response Schema

```json
{
  "insights": [
    {
      "title": "Client A brand voice: no exclamation marks",
      "content": "Client A's review feedback consistently removes exclamation marks. Their brand voice is understated and professional. Avoid enthusiastic punctuation.",
      "source_artifact": "uuid-artifact-123"
    }
  ],
  "cautions": [
    {
      "title": "Avoid assuming USD for pricing comparisons",
      "content": "User corrected a pricing table from USD to EUR. When the brief doesn't specify currency, ask via assumption tag rather than defaulting to USD.",
      "source_artifact": "uuid-artifact-456"
    }
  ],
  "obsolete_skills": [
    {
      "skill_id": "uuid-skill-789",
      "reason": "This preference was contradicted by recent user feedback — user now prefers tables over bullet lists for data."
    }
  ]
}
```

### 9.4 Post-Reflection Processing

1. **Insert new skill entries:** Each insight → `agent_skills` row with `category = 'skill'`. Each caution → `agent_skills` row with `category = 'work_learning'`.
2. **Remove obsolete entries:** Delete `agent_skills` rows identified in `obsolete_skills`.
3. **Check token budget:** If total exceeds 8,000 → trigger compaction (Section 5.3).
4. **Update agent metadata:**
   - `agent.last_reflection_at = now()`
   - `agent.completed_artifacts += N` (number of artifacts in this batch)
   - Recalculate `agent.progression_level` based on thresholds
5. **Update agent status:** `reflecting` → `ready`

### 9.5 Sequential Locking

As defined in TDD-02 Section 6.2: reflection acquires `SELECT ... FOR UPDATE` on the agent row. A second concurrent reflection on the same agent blocks until the first commits.

---

## 10. Knowledge Readiness Scoring

### 10.1 Heuristic Formula

Readiness is a synchronous DB calculation. No LLM call.

```python
async def compute_readiness_score(agent_id: str, project_id: str | None) -> int:
    """
    Compute agent readiness score (0-100).

    Components:
    - has_skills (40 points): agent has at least 1 skill entry
    - has_briefing (30 points): agent has ingested the current project brief
    - onboarding_complete (20 points): agent status has moved past 'learning' at least once
    - has_learnings (10 points): agent has at least 1 work_learning entry
    """
    score = 0

    skill_count = await db.scalar(
        select(func.count()).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.category == "skill"
        )
    )
    if skill_count > 0:
        score += 40

    if project_id:
        briefing_count = await db.scalar(
            select(func.count()).where(
                AgentSkill.agent_id == agent_id,
                AgentSkill.category == "briefing"
            )
        )
        if briefing_count > 0:
            score += 30
    else:
        score += 30  # No project context needed = full credit

    agent = await db.get(Agent, agent_id)
    if agent.completed_artifacts > 0 or agent.status != "learning":
        score += 20

    learning_count = await db.scalar(
        select(func.count()).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.category == "work_learning"
        )
    )
    if learning_count > 0:
        score += 10

    return score
```

### 10.2 Threshold Mapping

| Score | Level | Auto-Assembly Eligible |
|---|---|---|
| 0-49 | `insufficient` | No — excluded from auto-assembly |
| 50-79 | `partial` | Yes — minimum gate |
| 80-100 | `sufficient` | Yes — fully prepared |

In practice, an agent reaches `partial` (50+) as soon as it has skills (40) + has passed learning (20) = 60 points. Full readiness (100) requires project briefing + work learnings.

---

## 11. Initial Agent Learning Phase

### 11.1 Trigger

When an agent is created (onboarding or manual add), it enters `learning` status and the system enqueues a learning Celery task.

### 11.2 Learning Task

```
Task: execute_agent_learning(agent_id: str)

Lifecycle:
1. Load agent from DB
2. Set agent.status = 'learning'
3. Build learning prompt:
   - System: "You are {agent.name}, a {agent.specialization}. You are in your
     onboarding phase. Your goal is to build foundational knowledge about your
     domain so you can execute tasks effectively."
   - User: "Research your specialization in the context of this company:
     {workspace.domain_description}. Tech stack: {workspace.tech_stack}.

     Produce a core skills document covering:
     - Key concepts and best practices in your domain
     - Common patterns and conventions for this tech stack
     - Industry standards and quality benchmarks

     Use web_search and web_browser to research. Be thorough but concise.
     Output your findings as a structured markdown document."
4. Run agent loop with tools: [web_search, web_browser, file_write]
5. Parse output → create agent_skills row(s) with category = 'skill'
6. Compute readiness score
7. Set agent.status = 'ready', agent.readiness_score = computed score
```

### 11.3 Project Briefing

When a project brief is published (or updated), all roster agents receive a briefing:

```python
async def brief_all_agents(project: Project):
    agents = await get_active_roster(project.workspace_id)
    for agent in agents:
        # Delete existing briefing for this project
        await db.execute(
            delete(AgentSkill).where(
                AgentSkill.agent_id == agent.id,
                AgentSkill.category == "briefing",
                AgentSkill.title == f"Project: {project.name}"
            )
        )
        # Insert new briefing
        briefing = AgentSkill(
            agent_id=agent.id,
            category="briefing",
            title=f"Project: {project.name}",
            content=project.brief_published,
            token_count=count_tokens(project.brief_published),
        )
        db.add(briefing)
    await db.commit()
```

Briefings are NOT counted against the 8k memory budget. They are injected at position 7 of the user message (Section C: Current Task).

---

## 12. Compilation Logic

### 12.1 When to Compile

A compile step is added to the DAG **only** when a wave has ≥ 2 slots whose outputs need to be merged into the final artifact. This is determined by the DAG template's `needs_compile` flag.

### 12.2 When NOT to Compile

If the DAG is linear (each wave has one slot) or the final wave has a single agent, that agent's output IS the artifact. No compile step needed.

**Examples:**
- `content_research`: Wave 2 has one `writer` → Wave 3 has one `editor`. The editor's output is the artifact. No compile.
- `code_feature`: Wave 2 has one `implementation` → Wave 3 has one `qa_review`. The QA agent outputs the corrected code + report. The code files are the artifact. No compile.
- `multi_research`: Wave 1 has two parallel `researcher` slots → Wave 2 has one `compiler`. The compiler merges both. `needs_compile = false` because the compiler IS the final wave — it's built into the template structure, not bolted on.

### 12.3 Compile Slot Prompt

When a template does set `needs_compile = true`, the compile slot receives ALL upstream outputs and is prompted:

```
## Your Task
You are the Compiler. Multiple agents have produced outputs in parallel.
Your job is to merge them into a single, coherent deliverable.

Rules:
- Preserve all citations and sources from upstream outputs.
- Resolve any contradictions between upstream outputs (prefer the more specific
  or better-sourced claim).
- Maintain a consistent voice and structure throughout.
- Do NOT add new information — only organize and merge what was produced.
- Output the final deliverable in its entirety.
```

---

## 13. End-to-End Execution Flow

Tying all sections together. This is the complete lifecycle of a single `execute_artifact_dag` Celery task:

```
1. LOAD
   ├── Load ExecutionWave from DB (dag_plan, assembled_team)
   ├── Load Artifact (brief fields, budget)
   ├── Load Project (published brief)
   └── Set wave.status = 'running'

2. FOR EACH WAVE in dag_plan.waves (sequentially):
   │
   ├── 2a. Update heartbeat (wave.current_step, cost)
   │
   ├── 2b. FOR EACH SLOT in wave (concurrently via asyncio.gather):
   │   │
   │   ├── Load Agent from DB (name, specialization, system_prompt, model_tier)
   │   ├── Load Agent Memory (skills + work_learnings from agent_skills table)
   │   ├── Build Upstream Context (from wave_outputs dict, 15k cap)
   │   ├── Build Tools List (phase = 'execution', include MCP + Git if configured)
   │   │
   │   ├── Assemble Prompt:
   │   │   ├── SYSTEM: role + auto-assume + output format rules
   │   │   └── USER:  skills → learnings → upstream → project brief → artifact brief → task
   │   │              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   │   │              Recency Bias Rule: current task is ALWAYS LAST
   │   │
   │   ├── Run Agent Loop (Anthropic messages API with tool_use, max 15 iterations)
   │   ├── Extract Assumptions ([ASSUMPTION: ...] tags)
   │   ├── Extract Sources ([Source: ...] tags)
   │   ├── Collect Written Files (from file_write tool calls)
   │   └── Accumulate Token Usage + Cost
   │
   ├── 2c. Store wave outputs in memory (slot_id → WaveOutput)
   │
   └── 2d. CHECK CIRCUIT BREAKER
       └── If running_cost > artifact.max_budget_usd → ABORT

3. COMPILE (if template.needs_compile)
   └── Run compile agent with all upstream outputs

4. FINALIZE
   ├── Merge all file outputs across waves (later wave wins on conflict)
   ├── Upload files to S3: artifacts/{artifact_id}/v{version}/{filepath}
   ├── Create ArtifactVersion row (file_manifest, costs, assumptions, sources)
   ├── Update Artifact (status = 'in_review', current_version++, total_cost_usd)
   ├── For code artifacts: push to git branch, create/update PR
   ├── Update ExecutionWave (status = 'completed', costs, timestamps)
   └── Update Workspace.monthly_spend_usd (atomic increment)

5. ERROR PATH (if any step fails after retries)
   ├── ExecutionWave.status = 'failed', error_message = reason
   ├── Artifact stays in 'drafting' with error surfaced to user
   └── No ArtifactVersion created (clean failure — no partial artifacts)
```

---

## 14. Verification Checklist

- [ ] Sufficiency check returns valid JSON with `eligible`, `score`, and `issues` array within 4 seconds (Sonnet)
- [ ] Router call selects correct template AND maps agents to slots in one Haiku call within 2 seconds
- [ ] All 5 MVP DAG templates are registered and the router can select each one given appropriate briefs
- [ ] Prompt assembly follows the exact recency bias order: system → [skills, learnings] → upstream → project brief → artifact brief → task
- [ ] Agent skills + work learnings stay within 8,000 token budget; compaction triggers when ceiling is approached
- [ ] Compaction produces smaller output than input and preserves specific, hard-won knowledge
- [ ] Auto-assume rule is present in every agent's system prompt; assumptions are extracted via regex and stored in ArtifactVersion
- [ ] Upstream context injection respects the 15,000 token cap with middle-out truncation
- [ ] Tool availability is correctly gated by phase (no MCP during learning, no web_search during reflection)
- [ ] Reflection extracts new insights and cautions, removes obsolete skills, and respects the FOR UPDATE lock
- [ ] Knowledge readiness score computes correctly: 40 (skills) + 30 (briefing) + 20 (onboarding) + 10 (learnings) = 100
- [ ] Initial learning phase produces skill entries and transitions agent from `learning` to `ready`
- [ ] Iteration prompt correctly injects previous version + user feedback and produces a targeted update
- [ ] End-to-end: brief → sufficiency check → route → execute DAG → S3 upload → ArtifactVersion → status transition
