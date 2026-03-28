"""DAG template: simple_prose — write a document (no research phase needed).

Ref: TDD-03 Section 2.3 (simple_prose template definition).

Wave structure:
  Wave 1 — writer
  Wave 2 — editor (depends on wave 1)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

SIMPLE_PROSE_TEMPLATE = DagTemplate(
    template_id="simple_prose",
    name="Simple Prose",
    description=(
        "Write a document without a research phase. "
        "Best for briefs where the user has already provided enough context and "
        "the deliverable is a straightforward written document (email, blog post, "
        "internal memo, documentation)."
    ),
    artifact_type="prose",
    waves=(
        DagWave(
            wave_number=1,
            label="Writing the deliverable",
            slots=(
                DagSlot(
                    slot_id="writer",
                    label="Writer",
                    role_prompt=(
                        "Write the deliverable as described in the brief. Follow the goal, "
                        "target audience, and constraints exactly. Output the complete document."
                    ),
                    suggested_specializations=("Content Writer", "Technical Writer"),
                ),
            ),
            depends_on=(),
        ),
        DagWave(
            wave_number=2,
            label="Editorial review",
            slots=(
                DagSlot(
                    slot_id="editor",
                    label="Editor",
                    role_prompt=(
                        "Review for clarity, tone, structure, and completeness. Fix any issues "
                        "directly — output the final, polished document."
                    ),
                    suggested_specializations=("Content Writer", "QA Engineer"),
                ),
            ),
            depends_on=("writer",),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    required_roles=frozenset({
        "Content Writer",
        "Technical Writer",
        "QA Engineer",
    }),
)
