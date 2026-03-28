"""DAG template: multi_research — parallel research tracks merged by a compiler.

Ref: TDD-03 Section 2.3 (multi_research template definition).

Wave structure:
  Wave 1 — researcher_a + researcher_b (parallel)
  Wave 2 — compiler (depends on wave 1)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

MULTI_RESEARCH_TEMPLATE = DagTemplate(
    template_id="multi_research",
    name="Multi-Track Research",
    description=(
        "Multiple researchers work in parallel, then a compiler merges. "
        "Best for briefs that require exploring a topic from multiple angles "
        "or dimensions simultaneously and synthesizing the findings."
    ),
    artifact_type="prose",
    waves=(
        DagWave(
            wave_number=1,
            label="Parallel research tracks",
            slots=(
                DagSlot(
                    slot_id="researcher_a",
                    label="Researcher A",
                    role_prompt=(
                        "Research track A as defined in the brief. Focus on your assigned "
                        "dimension. Cite all sources. Output structured findings."
                    ),
                    suggested_specializations=("Research Analyst",),
                ),
                DagSlot(
                    slot_id="researcher_b",
                    label="Researcher B",
                    role_prompt=(
                        "Research track B as defined in the brief. Focus on your assigned "
                        "dimension. Cite all sources. Output structured findings."
                    ),
                    suggested_specializations=("Research Analyst", "Data Analyst"),
                ),
            ),
            depends_on=(),
        ),
        DagWave(
            wave_number=2,
            label="Compiling & synthesizing",
            slots=(
                DagSlot(
                    slot_id="compiler",
                    label="Compiler",
                    role_prompt=(
                        "Merge the research from both tracks into a unified, coherent "
                        "deliverable. Resolve any contradictions. Maintain all citations. "
                        "Follow the brief's structure requirements."
                    ),
                    suggested_specializations=("Strategy Analyst", "Content Writer"),
                ),
            ),
            depends_on=("researcher_a", "researcher_b"),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    required_roles=frozenset({
        "Research Analyst",
        "Data Analyst",
        "Strategy Analyst",
        "Content Writer",
    }),
)
