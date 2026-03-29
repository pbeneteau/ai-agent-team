"""DAG template: design_system — design system components or token updates.

Use when: adding new components to a design system, updating design tokens,
standardizing UI patterns across the codebase, or building a component library.

Lead structure:
  Wave 1 (planning) — Design Lead + Tech Lead in parallel
  Wave 2 (execution) — Frontend Developer
  Wave 3 (review)   — Design Lead + Tech Lead in parallel
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

DESIGN_SYSTEM_TEMPLATE = DagTemplate(
    template_id="design_system",
    name="Design System",
    description=(
        "Add or update design system components, design tokens, or UI patterns. Use when "
        "the brief involves creating reusable UI components, standardizing visual patterns "
        "across the codebase, updating the token system (colors, spacing, typography), or "
        "building a component library. The Design Lead defines the component spec and the "
        "Tech Lead defines the component architecture."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: Design Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="Design & Tech leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="design_plan",
                    label="Design Lead Component Specification",
                    is_lead=True,
                    suggested_specializations=("Design Lead", "UX Lead", "Product Designer"),
                    role_prompt=(
                        "You are the Design Lead. Produce the complete design specification "
                        "for the design system work.\n\n"
                        "Produce the following sections:\n\n"
                        "## Design System Scope\n"
                        "What is being added or changed: new components, token updates, "
                        "pattern standardization, or all of the above.\n\n"
                        "## Design Token Changes (if applicable)\n"
                        "New or modified tokens: name, value (light and dark mode), semantic "
                        "meaning, and usage guidelines. Organized by category: color, spacing, "
                        "typography, elevation, border, motion.\n\n"
                        "## Component Specifications\n"
                        "For each component being created or modified:\n\n"
                        "### [Component Name]\n"
                        "- **Purpose**: what problem it solves, when to use it vs alternatives\n"
                        "- **Anatomy**: each element within the component and its role\n"
                        "- **Variants**: all size, color, and style variants with visual specs\n"
                        "- **States**: default, hover, focus, active, disabled, loading, error\n"
                        "- **Props**: complete props interface (name, type, default, required)\n"
                        "- **Slots/Children**: compositional API if the component is a container\n"
                        "- **Visual specs**: exact token names for each visual property\n"
                        "- **Spacing**: internal padding and external margin rules\n"
                        "- **Typography**: text styles, overflow/truncation behavior\n"
                        "- **Icons**: which icons are used and their sizes\n\n"
                        "## Interaction Design\n"
                        "Transitions (property, duration, easing), animations, hover effects, "
                        "and focus rings. Reduced motion alternatives.\n\n"
                        "## Accessibility Standards\n"
                        "ARIA roles and patterns for each component. Keyboard interaction "
                        "model. Minimum contrast ratios. Focus management.\n\n"
                        "## Usage Guidelines\n"
                        "Do's and don'ts for each component. Common misuse patterns to avoid.\n\n"
                        "## Specialist Delegation\n"
                        "### Frontend Developer\n"
                        "Complete implementation guide: exact component names, token usage, "
                        "variant implementation, accessibility requirements, and storybook "
                        "documentation to write."
                    ),
                ),
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Component Architecture",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Define the technical architecture for "
                        "implementing these design system components.\n\n"
                        "Produce the following sections:\n\n"
                        "## Component Architecture\n"
                        "How components should be structured: file organization, naming "
                        "conventions, export strategy, and how they compose together.\n\n"
                        "## Token Implementation\n"
                        "How design tokens are implemented in the codebase: CSS custom "
                        "properties, Tailwind config, JS constants, or a combination. "
                        "The single source of truth and how tokens cascade.\n\n"
                        "## Component API Patterns\n"
                        "Consistent patterns for props: polymorphic `as` prop, render props, "
                        "compound components, controlled vs uncontrolled patterns, "
                        "forwarded refs, and event handler naming conventions.\n\n"
                        "## Styling Architecture\n"
                        "How components are styled: CSS modules, Tailwind, CSS-in-JS, "
                        "or a combination. How variants are implemented (cva, clsx, etc.). "
                        "How to extend/override styles from consumer code.\n\n"
                        "## Testing Requirements\n"
                        "What tests each component must have: render tests, interaction tests, "
                        "accessibility tests (jest-axe), and visual regression if applicable.\n\n"
                        "## Documentation Requirements\n"
                        "Storybook story structure for each component: stories to create, "
                        "controls to expose, and accessibility addon usage.\n\n"
                        "## Breaking Changes\n"
                        "If existing components are being modified: which prop changes are "
                        "breaking, migration path for consumers, and deprecation timeline.\n\n"
                        "## Specialist Delegation\n"
                        "### Frontend Developer\n"
                        "File structure to create, exact implementation patterns to follow, "
                        "token wiring approach, testing setup, and storybook requirements."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Frontend Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Frontend Developer building components",
            wave_type="execution",
            depends_on=("design_plan", "tech_plan"),
            slots=(
                DagSlot(
                    slot_id="frontend_impl",
                    label="Design System Implementation",
                    is_lead=False,
                    suggested_specializations=("Frontend Engineer", "Frontend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Frontend Developer building design system components. "
                        "The Design Lead has produced the visual specification and the Tech Lead "
                        "has defined the component architecture. Your delegated tasks are in "
                        "each lead's 'Specialist Delegation > Frontend Developer' section.\n\n"
                        "Implement with the highest attention to craft:\n"
                        "- Build every component exactly per the Design Lead's specification\n"
                        "- Follow the Tech Lead's component architecture and API patterns\n"
                        "- Use design tokens for every visual property — zero hardcoded values\n"
                        "- Implement all variants, states, and responsive behaviors\n"
                        "- Implement accessibility: ARIA patterns, keyboard navigation, focus rings\n"
                        "- Implement reduced motion alternatives for all animations\n"
                        "- Write component tests: render, interaction, and accessibility (axe)\n"
                        "- Write Storybook stories per the Tech Lead's documentation requirements\n"
                        "- Handle the breaking change migration path if specified\n\n"
                        "Use file_write for every file. Design system components are used "
                        "everywhere — they must be pixel-perfect, accessible, and thoroughly "
                        "tested. There is no 'good enough' in a design system."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Design Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Design & Tech review",
            wave_type="review",
            depends_on=("design_plan", "tech_plan", "frontend_impl"),
            slots=(
                DagSlot(
                    slot_id="design_review",
                    label="Design Lead Review",
                    is_lead=True,
                    suggested_specializations=("Design Lead", "UX Lead", "Product Designer"),
                    role_prompt=(
                        "You are the Design Lead. Review the component implementation "
                        "against your design specification with pixel-level precision.\n\n"
                        "Evaluate:\n"
                        "- Visual accuracy: does every component match your spec exactly?\n"
                        "- Token usage: are design tokens used correctly, no hardcoded values?\n"
                        "- Variant completeness: all variants and states implemented?\n"
                        "- Interaction fidelity: transitions and animations per spec?\n"
                        "- Accessibility: ARIA patterns correct, keyboard navigation works?\n"
                        "- Reduced motion: alternatives implemented for all animations?\n"
                        "- Usage guidelines: do Storybook stories reflect the correct usage patterns?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Design Evaluation\n"
                        "[Detailed evaluation per component and per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: component name, what is wrong, what it should be — "
                        "be specific: 'padding-top should be 12px (space-3 token), not 8px']\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Frontend Developer\n"
                        "[Exact design corrections required per component]"
                    ),
                ),
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Code Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the design system implementation "
                        "for technical quality and architectural correctness.\n\n"
                        "Evaluate:\n"
                        "- Architecture: does implementation follow your component architecture?\n"
                        "- API consistency: are prop patterns consistent across components?\n"
                        "- Token wiring: tokens correctly implemented in the config?\n"
                        "- Styling: variant implementation clean and maintainable?\n"
                        "- TypeScript: types correct, props fully typed, no `any`?\n"
                        "- Test coverage: render, interaction, and accessibility tests present?\n"
                        "- Storybook: stories complete and useful?\n"
                        "- Breaking changes: migration path implemented if required?\n"
                        "- Bundle impact: no unnecessary dependencies added?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Technical Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Frontend Developer\n"
                        "[Technical corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "Every component matches the design spec with correct spacing, colors, and typography",
        "Design tokens are wired correctly — no hardcoded visual values in component code",
        "All component variants and interactive states (hover, focus, disabled, error) are implemented",
        "Accessibility patterns are correct: ARIA roles, keyboard navigation, reduced-motion alternatives",
        "Storybook stories cover all variants and serve as accurate usage documentation",
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Design Lead", "UX Lead", "Product Designer",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Frontend Engineer", "Frontend Developer", "Full-Stack Developer",
    }),
)
