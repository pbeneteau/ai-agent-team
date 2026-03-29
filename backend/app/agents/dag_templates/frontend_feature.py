"""DAG template: frontend_feature — pure UI/frontend feature, existing API.

Use when: building a new screen, page, component, or UI flow that consumes an
existing API. No backend work needed — the contract already exists.

Lead structure:
  Wave 1 (planning) — PM Lead + Design Lead in parallel
  Wave 2 (execution) — Frontend Developer
  Wave 3 (review)   — Tech Lead + Design Lead in parallel
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

FRONTEND_FEATURE_TEMPLATE = DagTemplate(
    template_id="frontend_feature",
    name="Frontend Feature",
    description=(
        "Build a pure frontend feature: new screen, page, component, or UI flow "
        "that consumes an existing backend API. Use when no backend changes are "
        "needed. The PM Lead defines UX requirements, the Design Lead produces the "
        "component spec, and a frontend specialist implements. Both Tech Lead and "
        "Design Lead review the result."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: PM Lead + Design Lead (parallel)
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
                        "You are the Product Manager lead for this frontend feature. Define "
                        "the complete UX requirements and user experience contract.\n\n"
                        "Produce the following sections:\n\n"
                        "## User Problem\n"
                        "What user need does this UI solve? Who is the primary user?\n\n"
                        "## User Flows\n"
                        "Step-by-step description of every flow the user can take: "
                        "entry points, decision points, success outcomes, error outcomes, "
                        "and navigation paths.\n\n"
                        "## Functional Requirements\n"
                        "Every behavior the UI must exhibit: interactions, validations, "
                        "state transitions, loading behaviors, error displays, empty states.\n\n"
                        "## API Integration Points\n"
                        "Which existing API endpoints does this UI consume? Document: "
                        "endpoint, when it is called, what data it provides, and how errors "
                        "should be surfaced to the user.\n\n"
                        "## Acceptance Criteria\n"
                        "Given/When/Then for every functional requirement. Must be testable "
                        "from a user perspective.\n\n"
                        "## Specialist Delegation\n"
                        "### Frontend Developer\n"
                        "Which flows to build, which API endpoints to integrate, validation "
                        "rules, error handling UX, and acceptance criteria to satisfy."
                    ),
                ),
                DagSlot(
                    slot_id="design_plan",
                    label="Design Lead Planning",
                    is_lead=True,
                    suggested_specializations=("Design Lead", "UX Lead", "Product Designer"),
                    role_prompt=(
                        "You are the Design Lead for this frontend feature. Produce a "
                        "complete, unambiguous component and UX specification.\n\n"
                        "Produce the following sections:\n\n"
                        "## Component Architecture\n"
                        "Component tree for this feature: which components to create (new) "
                        "vs reuse (existing), parent-child relationships, and data flow.\n\n"
                        "## Component Specifications\n"
                        "For each new component:\n"
                        "- Purpose and responsibility\n"
                        "- Props interface (name, type, required/optional, default)\n"
                        "- Visual states: default, hover, focus, active, disabled, loading, error\n"
                        "- Slot/children API if composable\n\n"
                        "## Visual Design\n"
                        "Layout structure, spacing (use design token names), typography scale, "
                        "color usage (tokens only — no hex values), border radius, shadows, "
                        "and iconography.\n\n"
                        "## Interaction Design\n"
                        "Click behaviors, hover effects, transitions (duration + easing), "
                        "animations, drag behaviors, keyboard shortcuts if any.\n\n"
                        "## Responsive Design\n"
                        "Behavior at each breakpoint: what changes, what collapses, what "
                        "reflows. Mobile-first or desktop-first decision.\n\n"
                        "## Accessibility\n"
                        "ARIA roles, labels, and descriptions. Focus order. Keyboard "
                        "navigation pattern. Screen reader announcements for dynamic content.\n\n"
                        "## Specialist Delegation\n"
                        "### Frontend Developer\n"
                        "Precise implementation guide: exact component names to create, "
                        "styling approach, animation implementations, and design tokens to use."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Frontend Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Frontend implementation",
            wave_type="execution",
            depends_on=("pm_plan", "design_plan"),
            slots=(
                DagSlot(
                    slot_id="frontend_impl",
                    label="Frontend Implementation",
                    is_lead=False,
                    suggested_specializations=("Frontend Engineer", "Frontend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Frontend Developer. The PM Lead has defined the UX "
                        "requirements and the Design Lead has produced the component spec. "
                        "Your delegated task is in each lead's 'Specialist Delegation > "
                        "Frontend Developer' section.\n\n"
                        "Implement the complete frontend feature:\n"
                        "- Build every component per the Design Lead's spec\n"
                        "- Implement all user flows per the PM Lead's requirements\n"
                        "- Integrate all API endpoints as specified\n"
                        "- Handle loading, error, and empty states for every async operation\n"
                        "- Implement all form validations per the PM's rules\n"
                        "- Apply responsive behavior per the design breakpoints\n"
                        "- Implement all accessibility requirements\n"
                        "- Apply design tokens — never hardcode colors or spacing\n"
                        "- Follow the existing component patterns in the codebase\n\n"
                        "Use file_write for every file. Name components exactly as the Design "
                        "Lead specified. Do not deviate from the design spec without noting why. "
                        "Write component tests for every new component."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Tech Lead + Design Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Tech & Design review",
            wave_type="review",
            depends_on=("pm_plan", "design_plan", "frontend_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the frontend implementation for "
                        "technical correctness and code quality.\n\n"
                        "Evaluate:\n"
                        "- Code quality: component structure, separation of concerns, no dead code\n"
                        "- Performance: no unnecessary re-renders, proper memoization, lazy loading\n"
                        "- API integration: correct error handling, loading states, data mapping\n"
                        "- State management: appropriate scope, no prop drilling, no memory leaks\n"
                        "- Accessibility: ARIA attributes correct, keyboard navigation works\n"
                        "- Test coverage: components tested, user interactions tested\n"
                        "- Security: no XSS risks, no sensitive data in client state\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Frontend Developer\n"
                        "[Specific changes required]"
                    ),
                ),
                DagSlot(
                    slot_id="design_review",
                    label="Design Lead Review",
                    is_lead=True,
                    suggested_specializations=("Design Lead", "UX Lead", "Product Designer"),
                    role_prompt=(
                        "You are the Design Lead. Review the frontend implementation against "
                        "your design specification.\n\n"
                        "Evaluate:\n"
                        "- Visual accuracy: does the implementation match your component specs?\n"
                        "- Design token usage: are tokens used correctly, no hardcoded values?\n"
                        "- Spacing and layout: are spacing rules and grid followed?\n"
                        "- Interactive states: hover, focus, active, disabled all implemented?\n"
                        "- Responsive behavior: does it adapt correctly at each breakpoint?\n"
                        "- Animation fidelity: are transitions and animations per spec?\n"
                        "- Accessibility: are ARIA labels and keyboard behavior correct?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: component name, what is wrong, what it should be]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Frontend Developer\n"
                        "[Specific design corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "All UI components render correctly with proper visual states (loading, error, empty)",
        "Design tokens are used throughout — no hardcoded colors, spacing, or font sizes",
        "Responsive behavior works at all specified breakpoints",
        "Keyboard navigation and ARIA attributes are correctly implemented",
        "API integration handles errors gracefully with user-visible feedback",
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Design Lead", "UX Lead", "Product Designer",
        "Frontend Engineer", "Frontend Developer", "Full-Stack Developer",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
    }),
)
