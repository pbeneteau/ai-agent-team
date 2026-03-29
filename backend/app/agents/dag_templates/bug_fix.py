"""DAG template: bug_fix — diagnose and fix a reported bug.

Use when: a bug has been reported, a regression has been identified, or
unexpected behavior needs to be corrected in existing code.

Lead structure:
  Wave 1 (planning) — Tech Lead (diagnosis + fix strategy)
  Wave 2 (execution) — Developer
  Wave 3 (review)   — Tech Lead (verify fix + regression check)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

BUG_FIX_TEMPLATE = DagTemplate(
    template_id="bug_fix",
    name="Bug Fix",
    description=(
        "Diagnose and fix a reported bug or regression. Use when the brief describes "
        "unexpected behavior, an error, a crash, or a test failure in existing code. "
        "The Tech Lead diagnoses the root cause and plans the fix before a developer "
        "implements it. The Tech Lead then verifies the fix and checks for regressions."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: Tech Lead (diagnosis)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="Tech Lead diagnosing",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Diagnosis & Fix Plan",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. A bug has been reported. Your job is to "
                        "diagnose the root cause and produce a precise fix plan for the "
                        "developer to execute.\n\n"
                        "Produce the following sections:\n\n"
                        "## Bug Summary\n"
                        "Restate the bug clearly: what behavior is observed, what behavior "
                        "is expected, and under what conditions the bug occurs.\n\n"
                        "## Root Cause Analysis\n"
                        "Identify the exact root cause: which file, function, or logic is "
                        "wrong and why. Do not guess — reason through the code paths. "
                        "If multiple root causes exist, list them all.\n\n"
                        "## Affected Surface\n"
                        "List all files, functions, and systems affected by this bug and "
                        "by the proposed fix. Identify any downstream impact.\n\n"
                        "## Fix Strategy\n"
                        "Step-by-step description of what must change: which files to edit, "
                        "what logic to add/remove/modify, and why this fixes the root cause.\n\n"
                        "## Regression Risk\n"
                        "What existing functionality could break as a result of this fix? "
                        "How should the developer verify no regressions are introduced?\n\n"
                        "## Test Plan\n"
                        "Which tests to add or update. Describe: the specific scenario each "
                        "test covers, the input, and the expected output.\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "Exact implementation instructions: files to change, functions to "
                        "modify, logic to apply, and tests to write. Leave no ambiguity."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Developer fixing",
            wave_type="execution",
            depends_on=("tech_plan",),
            slots=(
                DagSlot(
                    slot_id="dev_impl",
                    label="Bug Fix Implementation",
                    is_lead=False,
                    suggested_specializations=(
                        "Backend Engineer", "Frontend Engineer", "Full-Stack Developer",
                        "Backend Developer", "Frontend Developer",
                    ),
                    role_prompt=(
                        "You are the Developer assigned to fix this bug. The Tech Lead has "
                        "diagnosed the root cause and provided a precise fix plan. "
                        "Your delegated task is in the Tech Lead's 'Specialist Delegation > "
                        "Developer' section.\n\n"
                        "Execute the fix precisely:\n"
                        "- Apply exactly the changes the Tech Lead described — no more, no less\n"
                        "- Do not refactor surrounding code unless required for the fix\n"
                        "- Write the regression tests the Tech Lead specified\n"
                        "- Update any existing tests that the fix changes behavior for\n"
                        "- Add an inline comment on the fixed line explaining what was wrong\n"
                        "- If you discover the fix is more complex than planned, document why\n\n"
                        "Use file_write for every changed file. Output complete file contents, "
                        "not diffs. The fix should be minimal and surgical — no opportunistic "
                        "cleanup."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Tech Lead (verify fix)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Tech Lead verifying fix",
            wave_type="review",
            depends_on=("tech_plan", "dev_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Fix Verification",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Verify that the developer's fix correctly "
                        "addresses the root cause you diagnosed, and that no regressions "
                        "were introduced.\n\n"
                        "Evaluate:\n"
                        "- Root cause addressed: does the fix actually resolve the root cause?\n"
                        "- Fix scope: is the change minimal and surgical, or did the developer "
                        "over-engineer or under-implement?\n"
                        "- Regression safety: does the fix risk breaking anything else?\n"
                        "- Test coverage: are the right tests added? Do they actually verify "
                        "the fix and catch regressions?\n"
                        "- Code correctness: no new bugs introduced in the fix itself\n"
                        "- Edge cases: are related edge cases also handled?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area above]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file path, description, exact fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Developer\n"
                        "[What must be corrected and why]\n\n"
                        "APPROVE only when the bug is definitively fixed and no regressions "
                        "are introduced. MINOR_FIX for small corrections you can apply directly. "
                        "REVISE if the developer missed the root cause or introduced new issues."
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "The fix addresses the root cause, not just the symptom",
        "No regressions introduced in adjacent functionality",
        "Edge cases identified in the diagnosis are handled",
        "Regression tests are present and verify the fix",
    ),
    max_iterations=2,
    required_roles=frozenset({
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Backend Engineer", "Frontend Engineer", "Full-Stack Developer",
        "Backend Developer", "Frontend Developer",
    }),
)
