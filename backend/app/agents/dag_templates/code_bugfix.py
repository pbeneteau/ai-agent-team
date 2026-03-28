"""DAG template: code_bugfix — fix a bug with analysis and validation.

Ref: TDD-03 Section 2.3 (code_bugfix template definition).

Wave structure:
  Wave 1 — analyst
  Wave 2 — fixer (depends on wave 1)
  Wave 3 — validator (depends on waves 1 + 2)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

CODE_BUGFIX_TEMPLATE = DagTemplate(
    template_id="code_bugfix",
    name="Code Bug Fix",
    description=(
        "Fix a bug with product context and QA validation. "
        "Best for briefs that describe a specific bug, regression, or incorrect "
        "behavior that needs root-cause analysis, a targeted fix, and verification."
    ),
    artifact_type="code",
    waves=(
        DagWave(
            wave_number=1,
            label="Analyzing the bug",
            slots=(
                DagSlot(
                    slot_id="analyst",
                    label="Bug Analyst",
                    role_prompt=(
                        "Analyze the bug description. Define: root cause hypothesis, "
                        "reproduction steps, fix criteria, regression risk. "
                        "Output as structured markdown."
                    ),
                    suggested_specializations=("Product Expert", "QA Engineer"),
                ),
            ),
            depends_on=(),
        ),
        DagWave(
            wave_number=2,
            label="Implementing the fix",
            slots=(
                DagSlot(
                    slot_id="fixer",
                    label="Bug Fixer",
                    role_prompt=(
                        "Implement the fix based on the analysis. Address the root cause, "
                        "not just the symptom. Ensure fix criteria are met. "
                        "Output the changed code files."
                    ),
                    suggested_specializations=("Frontend Dev", "Backend Dev", "Full-Stack Dev"),
                ),
            ),
            depends_on=("analyst",),
        ),
        DagWave(
            wave_number=3,
            label="Validating the fix",
            slots=(
                DagSlot(
                    slot_id="validator",
                    label="Fix Validator",
                    role_prompt=(
                        "Validate the fix against the criteria from the analysis. "
                        "Check for regressions. Output a pass/fail report."
                    ),
                    suggested_specializations=("QA Engineer",),
                ),
            ),
            depends_on=("analyst", "fixer"),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    required_roles=frozenset({
        "Product Expert",
        "QA Engineer",
        "Frontend Dev",
        "Backend Dev",
        "Full-Stack Dev",
    }),
)
