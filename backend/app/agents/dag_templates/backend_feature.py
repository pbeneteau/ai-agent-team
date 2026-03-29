"""DAG template: backend_feature — pure server-side feature, no UI.

Use when: building an API, service, background job, data pipeline endpoint,
or any backend-only capability that has no frontend component.

Lead structure:
  Wave 1 (planning) — PM Lead + Tech Lead in parallel
  Wave 2 (execution) — Backend Developer
  Wave 3 (review)   — Tech Lead
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

BACKEND_FEATURE_TEMPLATE = DagTemplate(
    template_id="backend_feature",
    name="Backend Feature",
    description=(
        "Build a pure server-side feature: API endpoint, service, background job, "
        "webhook handler, or data pipeline. Use when there is no frontend component "
        "and the deliverable is entirely backend code. The PM Lead defines the "
        "contract and the Tech Lead designs the technical approach before a backend "
        "specialist implements."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: PM Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="PM & Tech Lead planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="pm_plan",
                    label="PM Lead Planning",
                    is_lead=True,
                    suggested_specializations=("Product Manager", "Product Lead", "PM"),
                    role_prompt=(
                        "You are the Product Manager lead for this backend feature. Define "
                        "the complete product contract that engineering will implement.\n\n"
                        "Produce the following sections:\n\n"
                        "## Problem Statement\n"
                        "Why does this backend capability need to exist? What consumer "
                        "(frontend, third-party, internal service) needs it and why?\n\n"
                        "## Functional Requirements\n"
                        "Numbered list of every behavior the backend must exhibit. Include: "
                        "input validation rules, business logic constraints, output format, "
                        "error responses, rate limits, and idempotency requirements.\n\n"
                        "## API Contract (if applicable)\n"
                        "For each endpoint: HTTP method, path, request body schema, query "
                        "params, response schema (success and error), and status codes.\n\n"
                        "## Acceptance Criteria\n"
                        "Given/When/Then statements for every requirement. Must be testable.\n\n"
                        "## Out of Scope\n"
                        "What this feature explicitly does NOT do.\n\n"
                        "## Specialist Delegation\n"
                        "### Backend Developer\n"
                        "What to build, the exact API contract to implement, business rules "
                        "to enforce, and which acceptance criteria to satisfy."
                    ),
                ),
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Planning",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead for this backend feature. Design the complete "
                        "technical approach before the specialist implements.\n\n"
                        "Produce the following sections:\n\n"
                        "## Architecture Overview\n"
                        "How this feature fits into the existing system: which layers it touches, "
                        "which services it calls, and how data flows through it.\n\n"
                        "## Data Model\n"
                        "New tables, columns, or indexes required. Migration strategy. "
                        "Relationship changes. Index choices with reasoning.\n\n"
                        "## Service & Layer Design\n"
                        "How to structure the code: which functions/classes to create, "
                        "what goes in the route handler vs service layer vs repository, "
                        "and how to keep concerns separated.\n\n"
                        "## Error Handling Strategy\n"
                        "Which error types to define, how to map domain errors to HTTP "
                        "responses, and what to log at each failure point.\n\n"
                        "## Performance Considerations\n"
                        "Query optimization, caching opportunities, pagination approach, "
                        "async vs sync execution decisions.\n\n"
                        "## Security Considerations\n"
                        "Auth requirements, input sanitization, rate limiting, and any "
                        "sensitive data handling rules.\n\n"
                        "## Testing Strategy\n"
                        "Which unit tests, integration tests, and edge cases the specialist "
                        "must cover.\n\n"
                        "## Specialist Delegation\n"
                        "### Backend Developer\n"
                        "Step-by-step implementation guide: exact file structure, function "
                        "signatures, patterns to follow, and pitfalls to avoid."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Backend Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Backend implementation",
            wave_type="execution",
            depends_on=("pm_plan", "tech_plan"),
            slots=(
                DagSlot(
                    slot_id="backend_impl",
                    label="Backend Implementation",
                    is_lead=False,
                    suggested_specializations=("Backend Engineer", "Backend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Backend Developer. The PM Lead has defined the product "
                        "contract and the Tech Lead has designed the technical approach. "
                        "Your delegated task is in each lead's 'Specialist Delegation > "
                        "Backend Developer' section.\n\n"
                        "Implement the complete backend feature:\n"
                        "- Follow the Tech Lead's architecture and layer design exactly\n"
                        "- Implement all endpoints per the PM Lead's API contract\n"
                        "- Enforce every business rule from the functional requirements\n"
                        "- Implement the data model and migrations per the Tech Lead's spec\n"
                        "- Handle all error cases with proper status codes and messages\n"
                        "- Write unit tests for all business logic\n"
                        "- Write integration tests for all endpoints\n"
                        "- Add inline comments for non-obvious logic\n\n"
                        "Use file_write for every file. Do not skip tests. "
                        "Never hardcode configuration — use environment variables or settings. "
                        "Follow the existing codebase patterns precisely."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Tech Lead
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Tech Lead review",
            wave_type="review",
            depends_on=("pm_plan", "tech_plan", "backend_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the backend implementation against "
                        "your technical plan and the PM's product requirements.\n\n"
                        "Evaluate:\n"
                        "- Architecture conformance: does the code follow the layer design you specified?\n"
                        "- API contract: do all endpoints match the PM's schema exactly?\n"
                        "- Business logic: are all functional requirements implemented correctly?\n"
                        "- Data model: are migrations correct, indexes appropriate, constraints enforced?\n"
                        "- Error handling: are all error cases handled with the right status codes?\n"
                        "- Security: auth checks present, input validated, no sensitive data in logs\n"
                        "- Performance: no N+1 queries, pagination implemented, no blocking I/O in async paths\n"
                        "- Test coverage: all business logic tested, edge cases covered, tests are meaningful\n"
                        "- Code quality: readable, maintainable, follows project conventions\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area above]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file path, description, exact fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Backend Developer\n"
                        "[Specific changes required with file references]\n\n"
                        "APPROVE only when the implementation fully satisfies the PM contract "
                        "and your technical design. MINOR_FIX for small corrections you can "
                        "apply directly. REVISE when significant rework is needed."
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "All API endpoints return correct status codes and response shapes per spec",
        "Business logic handles all functional requirements from the PM contract",
        "Database migrations are correct with appropriate indexes and constraints",
        "Input validation rejects malformed data with clear error messages",
        "Unit tests cover all business logic paths including edge cases",
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Backend Engineer", "Backend Developer", "Full-Stack Developer",
    }),
)
