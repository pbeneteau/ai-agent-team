"""DAG template: mobile_feature — native or cross-platform mobile feature.

Use when: building a feature for iOS, Android, or cross-platform (React Native,
Flutter) that may also require backend API changes to support the mobile client.

Lead structure:
  Wave 1 (planning) — PM Lead + Design Lead in parallel
  Wave 2 (execution) — Mobile Developer + Backend Developer in parallel (if API needed)
  Wave 3 (review)   — Tech Lead
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

MOBILE_FEATURE_TEMPLATE = DagTemplate(
    template_id="mobile_feature",
    name="Mobile Feature",
    description=(
        "Build a feature for iOS, Android, or cross-platform mobile (React Native, "
        "Flutter, etc.), including any required backend API changes. Use when the brief "
        "targets a mobile app screen, flow, or capability. The PM Lead defines the mobile "
        "UX requirements and the Design Lead produces mobile-specific component specs. "
        "Mobile and backend specialists implement in parallel."
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
                        "You are the Product Manager lead for this mobile feature. Define "
                        "the complete product requirements with mobile-specific considerations.\n\n"
                        "Produce the following sections:\n\n"
                        "## Feature Overview\n"
                        "What the feature does, who it's for, and why it's being built "
                        "for mobile specifically.\n\n"
                        "## User Flows\n"
                        "Every flow the user can take: entry points (deep link, tab, notification), "
                        "decision points, success states, error states, and exit points. "
                        "Account for mobile-specific entry points (push notifications, "
                        "share extensions, background refresh).\n\n"
                        "## Functional Requirements\n"
                        "Every behavior the feature must exhibit on mobile: gestures, "
                        "offline behavior, background/foreground transitions, permission "
                        "requests (camera, location, notifications), and deep link handling.\n\n"
                        "## API Requirements\n"
                        "Which new or modified API endpoints the mobile client needs. "
                        "Define: endpoint, request/response schema, pagination, and "
                        "offline-first caching strategy.\n\n"
                        "## Acceptance Criteria\n"
                        "Given/When/Then for every requirement. Include mobile-specific "
                        "scenarios: low connectivity, background refresh, permission denied.\n\n"
                        "## Platform Scope\n"
                        "Which platforms: iOS, Android, or both? Minimum OS versions. "
                        "Any platform-specific behavior differences.\n\n"
                        "## Specialist Delegation\n"
                        "### Mobile Developer\n"
                        "User flows to implement, platform scope, API endpoints to consume, "
                        "offline behavior, permissions to request, and acceptance criteria.\n\n"
                        "### Backend Developer\n"
                        "New or modified API endpoints, request/response schemas, and any "
                        "server-side logic needed to support the mobile client."
                    ),
                ),
                DagSlot(
                    slot_id="design_plan",
                    label="Design Lead Mobile UI Planning",
                    is_lead=True,
                    suggested_specializations=("Design Lead", "UX Lead", "Product Designer", "Mobile Design Lead"),
                    role_prompt=(
                        "You are the Design Lead producing the mobile UI specification. "
                        "Mobile design has unique constraints — follow platform conventions "
                        "and touch interaction patterns.\n\n"
                        "Produce the following sections:\n\n"
                        "## Screen Inventory\n"
                        "List every screen in this feature: screen name, purpose, and "
                        "which user flow it belongs to.\n\n"
                        "## Screen Specifications\n"
                        "For each screen:\n"
                        "- Layout structure (safe areas, scroll behavior, fixed vs scrolling elements)\n"
                        "- Component list with visual specs (size, spacing, color tokens, typography)\n"
                        "- Touch targets (minimum 44pt/48dp, hit areas)\n"
                        "- Gesture interactions (tap, swipe, long press, pinch)\n"
                        "- Loading states, skeleton screens, empty states, error states\n\n"
                        "## Navigation\n"
                        "Navigation pattern (stack, tab, modal, sheet, drawer). Transitions "
                        "and animations between screens. Back navigation behavior.\n\n"
                        "## Platform-Specific Design\n"
                        "iOS vs Android differences: navigation conventions (iOS back gesture "
                        "vs Android back button), component variants (iOS action sheet vs "
                        "Android bottom sheet), typography (SF Pro vs Roboto).\n\n"
                        "## Responsive Layout\n"
                        "Behavior on different screen sizes (small phones, large phones, "
                        "tablets if applicable). Orientation handling.\n\n"
                        "## Accessibility\n"
                        "VoiceOver/TalkBack labels, dynamic type support, minimum contrast "
                        "ratios, reduced motion support.\n\n"
                        "## Specialist Delegation\n"
                        "### Mobile Developer\n"
                        "Exact implementation guide: screen names to create, component "
                        "specs to build, navigation setup, animation specs, and platform "
                        "differences to handle."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Mobile Developer + Backend Developer (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Mobile & Backend building",
            wave_type="execution",
            depends_on=("pm_plan", "design_plan"),
            slots=(
                DagSlot(
                    slot_id="mobile_impl",
                    label="Mobile Implementation",
                    is_lead=False,
                    suggested_specializations=("Mobile Developer", "iOS Developer", "Android Developer", "React Native Developer", "Flutter Developer"),
                    role_prompt=(
                        "You are the Mobile Developer. The PM Lead has defined the product "
                        "requirements and the Design Lead has produced the mobile UI spec. "
                        "Your delegated tasks are in each lead's 'Specialist Delegation > "
                        "Mobile Developer' section.\n\n"
                        "Implement the complete mobile feature:\n"
                        "- Build every screen per the Design Lead's specification\n"
                        "- Implement all user flows per the PM Lead's requirements\n"
                        "- Integrate all API endpoints (handle loading, error, empty states)\n"
                        "- Implement offline behavior and local caching as specified\n"
                        "- Handle all permission requests with proper user messaging\n"
                        "- Implement all gesture interactions per the design spec\n"
                        "- Handle deep links, background refresh, and app lifecycle events\n"
                        "- Apply platform conventions (iOS/Android native patterns)\n"
                        "- Implement accessibility: VoiceOver/TalkBack labels, dynamic type\n"
                        "- Write unit tests for business logic and UI component tests\n\n"
                        "Use file_write for every file. Follow the existing mobile codebase "
                        "architecture. Use design tokens — no hardcoded colors or sizes."
                    ),
                ),
                DagSlot(
                    slot_id="backend_impl",
                    label="Backend API Implementation",
                    is_lead=False,
                    suggested_specializations=("Backend Engineer", "Backend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Backend Developer supporting this mobile feature. "
                        "Your delegated task is in the PM Lead's 'Specialist Delegation > "
                        "Backend Developer' section.\n\n"
                        "Implement the backend API support for the mobile client:\n"
                        "- Build all new or modified endpoints per the PM's API requirements\n"
                        "- Design responses for mobile efficiency (minimal payload, pagination)\n"
                        "- Implement push notification triggers if required\n"
                        "- Handle mobile-specific concerns: token refresh, device registration\n"
                        "- Write integration tests for all endpoints\n\n"
                        "Use file_write for every file. Mobile clients are bandwidth-sensitive — "
                        "keep response payloads minimal and paginate large lists."
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
            depends_on=("pm_plan", "design_plan", "mobile_impl", "backend_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer", "Mobile Lead"),
                    role_prompt=(
                        "You are the Tech Lead. Review the mobile and backend implementation "
                        "for quality and correctness.\n\n"
                        "Evaluate:\n"
                        "- Mobile code quality: follows platform conventions, no anti-patterns\n"
                        "- UI accuracy: screens match the design spec\n"
                        "- API integration: correct error handling, offline behavior, caching\n"
                        "- Performance: no janky animations, no blocking main thread, efficient "
                        "network calls and image loading\n"
                        "- Security: no sensitive data in logs, secure storage for tokens\n"
                        "- Backend quality: endpoints efficient, mobile-optimized payloads\n"
                        "- Test coverage: unit tests for logic, integration tests for API\n"
                        "- PM requirements: all acceptance criteria satisfied\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Mobile Developer\n"
                        "[Mobile corrections required]\n"
                        "### Backend Developer\n"
                        "[Backend corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "Mobile screens match the design spec and follow platform conventions",
        "API integration handles offline scenarios and network errors gracefully",
        "No blocking operations on the main thread — animations remain smooth",
        "Sensitive data uses secure storage, not plain text or logs",
        "All acceptance criteria from the PM spec are satisfied",
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Design Lead", "UX Lead", "Product Designer", "Mobile Design Lead",
        "Mobile Developer", "iOS Developer", "Android Developer",
        "React Native Developer", "Flutter Developer",
        "Backend Engineer", "Backend Developer", "Full-Stack Developer",
        "Tech Lead", "Engineering Manager", "Senior Engineer", "Mobile Lead",
    }),
)
