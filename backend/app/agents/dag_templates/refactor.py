"""DAG template: refactor — improve code structure without changing behavior.

Use when: code needs restructuring for maintainability, readability, or
performance, but the external behavior must remain identical.

Lead structure:
  Wave 1 (planning) — Tech Lead + PM Lead in parallel
  Wave 2 (execution) — Developer
  Wave 3 (review)   — Tech Lead
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

REFACTOR_TEMPLATE = DagTemplate(
    template_id="refactor",
    name="Code Refactor",
    description=(
        "Restructure existing code for maintainability, readability, or performance "
        "without changing observable behavior. Use when the brief calls for cleaning up "
        "technical debt, extracting abstractions, splitting large modules, improving "
        "naming, or optimizing internal logic while keeping the public API stable. "
        "The Tech Lead scopes the refactor and the PM Lead assesses impact and risk."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: Tech Lead + PM Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="Tech & PM leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Refactor Plan",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead planning this refactor. Your job is to "
                        "produce a precise technical plan that enables a safe, complete "
                        "refactor with zero behavior change.\n\n"
                        "Produce the following sections:\n\n"
                        "## Refactor Scope\n"
                        "Exactly which files, modules, classes, and functions are being "
                        "refactored. What is the entry point and what are the boundaries.\n\n"
                        "## Current Problems\n"
                        "Specific code smells or structural issues being addressed: "
                        "large classes, long functions, duplicated logic, poor naming, "
                        "missing abstractions, wrong layer placement, etc.\n\n"
                        "## Target Architecture\n"
                        "What the code should look like after the refactor: new file structure, "
                        "new abstraction layers, renamed symbols, extracted functions/classes, "
                        "and design patterns to apply.\n\n"
                        "## Refactor Steps\n"
                        "Ordered, atomic steps the developer must follow. Each step should be "
                        "independently verifiable. Order matters — steps must not break "
                        "intermediate states.\n\n"
                        "## Behavior Preservation Contract\n"
                        "Define exactly what must NOT change: public API signatures, external "
                        "behavior, return values, side effects, error contracts. This is the "
                        "invariant the developer must maintain throughout.\n\n"
                        "## Testing Strategy\n"
                        "Which existing tests cover this code. Which new tests to add to "
                        "lock in the current behavior before refactoring. Specify exactly "
                        "what each test must assert.\n\n"
                        "## Risk Areas\n"
                        "Where the refactor is most likely to introduce regressions. "
                        "What to double-check.\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "Step-by-step implementation guide with exact changes per file, "
                        "the behavior invariants to maintain, and the tests to run at each step."
                    ),
                ),
                DagSlot(
                    slot_id="pm_plan",
                    label="PM Lead Impact Assessment",
                    is_lead=True,
                    suggested_specializations=("Product Manager", "Product Lead", "PM"),
                    role_prompt=(
                        "You are the Product Manager lead assessing the impact of this refactor "
                        "on the product and users.\n\n"
                        "Produce the following sections:\n\n"
                        "## User-Facing Impact\n"
                        "Does this refactor have any risk of changing behavior the user can "
                        "observe? List any user-facing functionality that must be regression "
                        "tested after the refactor.\n\n"
                        "## API Stability\n"
                        "If any public API (endpoints, SDKs, events) is touched: confirm "
                        "it must remain backward-compatible. List consumers that depend on "
                        "the current contract.\n\n"
                        "## Rollout Risk\n"
                        "Assess the deployment risk: can this be deployed atomically, or "
                        "does it require a phased rollout or feature flag?\n\n"
                        "## Success Criteria\n"
                        "How will we know the refactor succeeded without breaking anything? "
                        "What metrics, tests, or manual verifications should pass?\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "Behavioral constraints to preserve, user-facing scenarios to verify, "
                        "and any rollout precautions to take."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Developer refactoring",
            wave_type="execution",
            depends_on=("tech_plan", "pm_plan"),
            slots=(
                DagSlot(
                    slot_id="dev_impl",
                    label="Refactor Implementation",
                    is_lead=False,
                    suggested_specializations=(
                        "Backend Engineer", "Frontend Engineer", "Full-Stack Developer",
                        "Backend Developer", "Frontend Developer",
                    ),
                    role_prompt=(
                        "You are the Developer executing this refactor. The Tech Lead has "
                        "defined the target architecture and steps. The PM Lead has defined "
                        "the behavioral constraints. Your delegated tasks are in each lead's "
                        "'Specialist Delegation > Developer' section.\n\n"
                        "Execute the refactor with discipline:\n"
                        "- Follow the Tech Lead's steps in order — do not skip or reorder\n"
                        "- Maintain the behavior preservation contract at every step\n"
                        "- Do not change public API signatures, return types, or error contracts\n"
                        "- Add the tests the Tech Lead specified before making changes\n"
                        "- Run tests mentally at each step — if a step would break a test, stop\n"
                        "- Rename symbols consistently across all files (no partial renames)\n"
                        "- Remove dead code, but do not add new features\n"
                        "- Leave the code strictly better than you found it — cleaner, not bigger\n\n"
                        "Use file_write for every file. Output the complete refactored file, "
                        "not diffs. Document non-obvious refactor decisions with inline comments."
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
            depends_on=("tech_plan", "pm_plan", "dev_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the refactored code against your "
                        "plan and verify behavioral preservation.\n\n"
                        "Evaluate:\n"
                        "- Structural goals: does the refactored code match the target architecture?\n"
                        "- Step adherence: were your refactor steps followed correctly?\n"
                        "- Behavior preservation: is the public API identical? No behavior changes?\n"
                        "- Test coverage: are the behavior-locking tests present and correct?\n"
                        "- Completeness: are all specified files refactored? Any partial renames?\n"
                        "- Code quality: is the result meaningfully better than the original?\n"
                        "- Regressions: any logic that was accidentally changed or removed?\n"
                        "- PM constraints: are user-facing behaviors and API contracts preserved?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, what is wrong, what it should be]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Developer\n"
                        "[Specific corrections required]\n\n"
                        "APPROVE only when the refactor is complete, clean, and behavior is "
                        "provably preserved. MINOR_FIX for small cleanups you can apply directly. "
                        "REVISE if steps were skipped, behavior was changed, or target "
                        "architecture was not reached."
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "Public API and external behavior are identical before and after the refactor",
        "All refactor steps from the plan are completed — no partial renames or half-migrated patterns",
        "Behavior-locking tests exist and pass, proving no regressions",
        "The refactored code is measurably better in the targeted dimension (readability, modularity, or performance)",
    ),
    max_iterations=2,
    required_roles=frozenset({
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Product Manager", "Product Lead", "PM",
        "Backend Engineer", "Frontend Engineer", "Full-Stack Developer",
        "Backend Developer", "Frontend Developer",
    }),
)
