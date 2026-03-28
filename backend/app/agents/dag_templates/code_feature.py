"""DAG template: code_feature — build a feature with product, design, and QA input.

Ref: TDD-03 Section 2.3 (code_feature template definition).

Wave structure:
  Wave 1 — product_spec + design_spec (parallel)
  Wave 2 — implementation (depends on wave 1)
  Wave 3 — qa_review (depends on waves 1 + 2)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

CODE_FEATURE_TEMPLATE = DagTemplate(
    template_id="code_feature",
    name="Code Feature Build",
    description=(
        "Build a feature with product, design, and QA input. "
        "Best for briefs that require implementing a new feature or UI component "
        "with clear product requirements. Produces code files plus a QA report."
    ),
    artifact_type="code",
    waves=(
        DagWave(
            wave_number=1,
            label="Defining requirements & design specs",
            slots=(
                DagSlot(
                    slot_id="product_spec",
                    label="Product Specification",
                    role_prompt=(
                        "Analyze the brief. Produce: user flows, functional requirements, "
                        "acceptance criteria, edge cases. Output as structured markdown."
                    ),
                    suggested_specializations=("Product Expert", "Product Manager"),
                ),
                DagSlot(
                    slot_id="design_spec",
                    label="Design Specification",
                    role_prompt=(
                        "Analyze the brief. Produce: component hierarchy, spacing/layout rules, "
                        "design tokens, accessibility requirements, responsive behavior. "
                        "Output as structured markdown."
                    ),
                    suggested_specializations=("Design Expert", "UX Designer"),
                ),
            ),
            depends_on=(),
        ),
        DagWave(
            wave_number=2,
            label="Implementing code",
            slots=(
                DagSlot(
                    slot_id="implementation",
                    label="Implementation",
                    role_prompt=(
                        "Implement the feature using the product requirements and design specs "
                        "provided as upstream context. Follow the design tokens exactly. "
                        "Satisfy all acceptance criteria. Output working code files."
                    ),
                    suggested_specializations=("Frontend Dev", "Backend Dev", "Full-Stack Dev"),
                ),
            ),
            depends_on=("product_spec", "design_spec"),
        ),
        DagWave(
            wave_number=3,
            label="Quality review",
            slots=(
                DagSlot(
                    slot_id="qa_review",
                    label="QA Review",
                    role_prompt=(
                        "Review the implementation against the product requirements and design "
                        "specs. Check: acceptance criteria coverage, edge case handling, "
                        "accessibility compliance, code quality. Output a QA report with "
                        "pass/fail per criterion and any issues found."
                    ),
                    suggested_specializations=("QA Engineer",),
                ),
            ),
            depends_on=("product_spec", "design_spec", "implementation"),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    required_roles=frozenset({
        "Product Expert",
        "Product Manager",
        "Design Expert",
        "UX Designer",
        "Frontend Dev",
        "Backend Dev",
        "Full-Stack Dev",
        "QA Engineer",
    }),
)
