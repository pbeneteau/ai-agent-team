"""DAG template: full_feature — complete product feature with UI and backend.

Use when: building a new user-facing feature that involves both frontend and
backend work, with product requirements and design specifications needed.

Lead structure:
  Wave 1 (planning) — PM Lead + Design Lead in parallel
  Wave 2 (execution) — Backend Dev + Frontend Dev in parallel
  Wave 3 (execution) — QA Engineer
  Wave 4 (review)   — Tech Lead
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

FULL_FEATURE_TEMPLATE = DagTemplate(
    template_id="full_feature",
    name="Full Product Feature",
    description=(
        "Build a complete user-facing feature with product requirements, design "
        "specifications, backend and frontend implementation, and QA. Use this "
        "template when the brief involves a new feature that has both a UI and "
        "server-side logic, and needs product + design sign-off before coding starts."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: PM Lead + Design Lead
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="PM & Design leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="pm_plan",
                    label="PM Lead Planning",
                    is_lead=True,
                    suggested_specializations=("Product Manager", "Product Lead", "PM"),
                    role_prompt=(
                        "You are the Product Manager lead for this feature. Your job is to "
                        "translate the brief into a precise, actionable product specification "
                        "that the engineering and design specialists can execute without "
                        "ambiguity.\n\n"
                        "Produce the following sections:\n\n"
                        "## Problem Statement\n"
                        "One paragraph on why this feature is needed, who it is for, and "
                        "what problem it solves.\n\n"
                        "## User Stories\n"
                        "Write every user story in the format: "
                        "'As a [user type], I want to [action] so that [outcome].' "
                        "Cover all primary flows and edge cases.\n\n"
                        "## Functional Requirements\n"
                        "Numbered list of every capability the system must have. "
                        "Be specific: state exact behaviors, not vague goals. "
                        "Include validation rules, error states, and empty states.\n\n"
                        "## Acceptance Criteria\n"
                        "For each user story, write testable acceptance criteria using "
                        "Given/When/Then format.\n\n"
                        "## Out of Scope\n"
                        "Explicitly list what is NOT included in this feature to prevent "
                        "scope creep.\n\n"
                        "## Data Model Impact\n"
                        "Identify any new or modified data entities, fields, or relationships "
                        "this feature requires.\n\n"
                        "## Specialist Delegation\n"
                        "### Backend Developer\n"
                        "Summarize the server-side work: which endpoints to build, data "
                        "contracts, business logic, validation rules, and constraints.\n\n"
                        "### Frontend Developer\n"
                        "Summarize the client-side work: which screens/components to build, "
                        "user flows, state management needs, and integration points with the API.\n\n"
                        "### QA Engineer\n"
                        "List the critical test scenarios covering happy paths, edge cases, "
                        "error states, and acceptance criteria verification."
                    ),
                ),
                DagSlot(
                    slot_id="design_plan",
                    label="Design Lead Planning",
                    is_lead=True,
                    suggested_specializations=("Design Lead", "UX Lead", "Product Designer"),
                    role_prompt=(
                        "You are the Design Lead for this feature. Your job is to define the "
                        "complete UX and UI specification that the frontend specialist will "
                        "implement exactly.\n\n"
                        "Produce the following sections:\n\n"
                        "## UX Flows\n"
                        "Describe every user flow step by step: entry points, decision points, "
                        "success states, error states, and exit points. Use numbered steps.\n\n"
                        "## Component Inventory\n"
                        "List every UI component needed (new or reused). For each: name, "
                        "purpose, props/variants, and interaction behavior.\n\n"
                        "## Layout & Spacing\n"
                        "Define the layout structure: grid system, spacing scale, alignment "
                        "rules, and responsive breakpoints. Reference design tokens where "
                        "applicable.\n\n"
                        "## Visual Specifications\n"
                        "Colors (use design tokens), typography scale, icon usage, elevation "
                        "and shadow rules, border radius. State variations: default, hover, "
                        "focus, disabled, error, loading.\n\n"
                        "## Accessibility Requirements\n"
                        "ARIA roles and labels, keyboard navigation order, focus management, "
                        "color contrast ratios, screen reader behavior.\n\n"
                        "## Responsive Behavior\n"
                        "How the layout adapts across breakpoints. What collapses, stacks, "
                        "or hides at each screen size.\n\n"
                        "## Interaction & Animation\n"
                        "Transitions, loading states, skeleton screens, micro-interactions. "
                        "Duration and easing for each.\n\n"
                        "## Specialist Delegation\n"
                        "### Frontend Developer\n"
                        "Precise implementation instructions: component structure, styling "
                        "approach, which design tokens to use, animation specs, and any "
                        "third-party UI library constraints to follow."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Backend Dev + Frontend Dev (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Backend & Frontend building",
            wave_type="execution",
            depends_on=("pm_plan", "design_plan"),
            slots=(
                DagSlot(
                    slot_id="backend_impl",
                    label="Backend Implementation",
                    is_lead=False,
                    suggested_specializations=("Backend Engineer", "Backend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Backend Developer. The PM Lead and Design Lead have "
                        "planned this feature. Your delegated task is in the PM Lead's "
                        "'Specialist Delegation > Backend Developer' section.\n\n"
                        "Implement all server-side code:\n"
                        "- API endpoints (routes, request validation, response schemas)\n"
                        "- Business logic and service layer\n"
                        "- Database models and migrations if needed\n"
                        "- Input validation and error handling\n"
                        "- Unit tests for all business logic\n\n"
                        "Use file_write to output every file. Follow the project's existing "
                        "conventions exactly. Do not invent new patterns — extend what exists. "
                        "Every endpoint must handle error cases explicitly. "
                        "Document non-obvious decisions with inline comments."
                    ),
                ),
                DagSlot(
                    slot_id="frontend_impl",
                    label="Frontend Implementation",
                    is_lead=False,
                    suggested_specializations=("Frontend Engineer", "Frontend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Frontend Developer. The PM Lead and Design Lead have "
                        "planned this feature. Your delegated task is in:\n"
                        "- PM Lead's 'Specialist Delegation > Frontend Developer' section\n"
                        "- Design Lead's 'Specialist Delegation > Frontend Developer' section\n\n"
                        "Implement all client-side code:\n"
                        "- UI components following the design spec exactly\n"
                        "- State management and data fetching\n"
                        "- API integration with the backend endpoints\n"
                        "- Form validation matching the PM's acceptance criteria\n"
                        "- Loading, error, and empty states for every async operation\n"
                        "- Responsive behavior per the design spec\n"
                        "- Accessibility: ARIA labels, keyboard navigation, focus management\n\n"
                        "Use file_write to output every file. Apply design tokens — never "
                        "hardcode colors or spacing values. Components must be composable "
                        "and follow the existing component patterns in the codebase."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Execution: QA Engineer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="QA verification",
            wave_type="execution",
            depends_on=("pm_plan", "design_plan", "backend_impl", "frontend_impl"),
            slots=(
                DagSlot(
                    slot_id="qa_check",
                    label="QA Engineering",
                    is_lead=False,
                    suggested_specializations=("QA Engineer", "Quality Engineer", "Test Engineer"),
                    role_prompt=(
                        "You are the QA Engineer. Review all implementation outputs against "
                        "the PM Lead's acceptance criteria and Design Lead's specifications.\n\n"
                        "Produce:\n\n"
                        "## Test Coverage Report\n"
                        "For each acceptance criterion from the PM plan: PASS, FAIL, or "
                        "PARTIAL — with a specific explanation for non-PASS items.\n\n"
                        "## Issues Found\n"
                        "List every issue with: severity (critical/major/minor), description, "
                        "reproduction steps, and expected vs actual behavior.\n\n"
                        "## Design Conformance\n"
                        "Check the frontend implementation against the design spec: spacing, "
                        "colors, component variants, responsive behavior, accessibility.\n\n"
                        "## Edge Case Verification\n"
                        "Verify all edge cases and error states are handled in both backend "
                        "and frontend code.\n\n"
                        "## Test Files\n"
                        "Write integration test files covering the critical user flows. "
                        "Use file_write to output them."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 4 — Review: Tech Lead
        # ------------------------------------------------------------------
        DagWave(
            wave_number=4,
            label="Tech Lead review",
            wave_type="review",
            depends_on=("pm_plan", "design_plan", "backend_impl", "frontend_impl", "qa_check"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review all outputs from this execution and "
                        "make a final quality decision.\n\n"
                        "Evaluate:\n"
                        "- Code quality: readability, maintainability, adherence to project conventions\n"
                        "- Architecture: correct layer separation, no anti-patterns, proper abstractions\n"
                        "- Security: no injection risks, proper auth checks, no sensitive data leaks\n"
                        "- Performance: no N+1 queries, no unnecessary re-renders, efficient algorithms\n"
                        "- Test coverage: critical paths tested, edge cases covered\n"
                        "- QA issues: are all critical/major issues from the QA report addressed?\n"
                        "- PM requirements: does the implementation satisfy all acceptance criteria?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area above]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[List every issue with file path, line reference if applicable, and "
                        "exact fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Backend Developer\n"
                        "[Specific changes required]\n"
                        "### Frontend Developer\n"
                        "[Specific changes required]\n"
                        "### QA Engineer\n"
                        "[Additional verification required]\n\n"
                        "APPROVE only when all critical and major issues are resolved. "
                        "Use MINOR_FIX for issues you can correct directly in the files. "
                        "Use REVISE when specialists must redo significant portions of their work."
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "All features specified in the brief are implemented and functional",
        "Code compiles and runs without errors",
        "API contracts match the PM specification (routes, status codes, response shapes)",
        "Frontend components render correctly with proper loading, error, and empty states",
        "No placeholder or stub implementations remain in the codebase",
        "Error handling covers all expected failure modes in both backend and frontend",
    ),
    validation_wave=DagWave(
        wave_number=0,
        label="Validating delegation plan",
        wave_type="validation",
        depends_on=("pm_plan", "design_plan"),
        slots=(
            DagSlot(
                slot_id="delegation_check",
                label="Delegation Validation",
                is_lead=True,
                suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                role_prompt=(
                    "Review the delegation plans from the PM Lead and Design Lead. "
                    "Verify that each specialist's assignment is specific enough to "
                    "produce working code without ambiguity."
                ),
            ),
        ),
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Design Lead", "UX Lead", "Product Designer",
        "Backend Engineer", "Backend Developer", "Full-Stack Developer",
        "Frontend Engineer", "Frontend Developer",
        "QA Engineer", "Quality Engineer", "Test Engineer",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
    }),
)
