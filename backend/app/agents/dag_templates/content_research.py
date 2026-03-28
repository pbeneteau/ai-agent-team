"""DAG template: content_research — research a topic and produce a written deliverable.

Ref: TDD-03 Section 2.3 (content_research template definition).

Wave structure:
  Wave 1 — researcher + framework_designer (parallel)
  Wave 2 — writer (depends on wave 1)
  Wave 3 — editor (depends on wave 2)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

CONTENT_RESEARCH_TEMPLATE = DagTemplate(
    template_id="content_research",
    name="Content Research & Writing",
    description=(
        "Research a topic and produce a written deliverable. "
        "Best for briefs that require gathering data, analyzing competitors or markets, "
        "and producing a structured document based on the findings."
    ),
    artifact_type="prose",
    waves=(
        DagWave(
            wave_number=1,
            label="Researching & gathering data",
            slots=(
                DagSlot(
                    slot_id="researcher",
                    label="Research Analyst",
                    role_prompt=(
                        "Perform web research on the topic defined in the brief. Gather data, "
                        "statistics, competitor information, market trends. Cite all sources "
                        "with URLs. Output a structured research brief."
                    ),
                    suggested_specializations=("Research Analyst", "Data Analyst"),
                ),
                DagSlot(
                    slot_id="framework_designer",
                    label="Framework Designer",
                    role_prompt=(
                        "Define the analysis framework: what dimensions to compare, what "
                        "structure the final document should follow, what questions it must "
                        "answer. Output as a document outline with section headers and "
                        "key questions per section."
                    ),
                    suggested_specializations=("Product Expert", "Strategy Analyst"),
                ),
            ),
            depends_on=(),
        ),
        DagWave(
            wave_number=2,
            label="Drafting the deliverable",
            slots=(
                DagSlot(
                    slot_id="writer",
                    label="Content Writer",
                    role_prompt=(
                        "Write the full deliverable using the research data and the analysis "
                        "framework. Follow the framework structure exactly. Cite sources from "
                        "the research. Make it comprehensive but concise."
                    ),
                    suggested_specializations=("Content Writer", "Strategy Analyst", "Technical Writer"),
                ),
            ),
            depends_on=("researcher", "framework_designer"),
        ),
        DagWave(
            wave_number=3,
            label="Editorial review",
            slots=(
                DagSlot(
                    slot_id="editor",
                    label="Editor",
                    role_prompt=(
                        "Review for clarity, consistency, factual accuracy, tone, and "
                        "completeness. Flag any unsupported claims. Suggest specific "
                        "improvements. Output the revised document."
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
        "Research Analyst",
        "Data Analyst",
        "Product Expert",
        "Strategy Analyst",
        "Content Writer",
        "Technical Writer",
        "QA Engineer",
    }),
)
