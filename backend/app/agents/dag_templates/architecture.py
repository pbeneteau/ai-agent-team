"""DAG template: architecture — major architectural change or system redesign.

Use when: making a significant architectural decision that affects multiple
systems, introducing a new pattern across the codebase, migrating to a new
technology, or redesigning a core component.

Lead structure:
  Wave 1 (planning) — PM Lead + Tech Lead in parallel
  Wave 2 (execution) — Developer(s)
  Wave 3 (review)   — Tech Lead
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

ARCHITECTURE_TEMPLATE = DagTemplate(
    template_id="architecture",
    name="Architecture Change",
    description=(
        "Implement a major architectural change: new system pattern, technology migration, "
        "core component redesign, or cross-cutting concern introduction. Use when the brief "
        "involves decisions that affect how multiple parts of the system work together — "
        "not just a single feature. The PM Lead assesses business constraints and the Tech "
        "Lead designs the architecture and migration path."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: PM Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="PM & Tech leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="pm_plan",
                    label="PM Lead Business Assessment",
                    is_lead=True,
                    suggested_specializations=("Product Manager", "Product Lead", "PM"),
                    role_prompt=(
                        "You are the Product Manager lead for this architectural change. "
                        "Define the business context, constraints, and success criteria.\n\n"
                        "Produce the following sections:\n\n"
                        "## Business Motivation\n"
                        "Why is this architectural change necessary now? What business "
                        "problem, technical constraint, or strategic goal drives it?\n\n"
                        "## Business Constraints\n"
                        "Non-negotiable constraints the architecture must satisfy: "
                        "zero downtime requirement, data migration window, SLA during "
                        "transition, backward compatibility with existing clients, "
                        "regulatory requirements.\n\n"
                        "## Success Criteria\n"
                        "How the business will measure success: performance targets, "
                        "reliability targets, developer velocity improvement, cost reduction.\n\n"
                        "## Risk Tolerance\n"
                        "What level of risk is acceptable during the transition? What "
                        "constitutes an unacceptable outcome that would trigger a rollback?\n\n"
                        "## Stakeholder Impact\n"
                        "Which teams or systems are affected by this change? Who must be "
                        "notified or involved?\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "Business constraints to respect during implementation, success "
                        "criteria to satisfy, and rollback triggers to design for."
                    ),
                ),
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Architecture Design",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Design the target architecture and the "
                        "migration path to reach it.\n\n"
                        "Produce the following sections:\n\n"
                        "## Current State Analysis\n"
                        "What exists today: the current architecture, its limitations, "
                        "technical debt involved, and why it must change.\n\n"
                        "## Target Architecture\n"
                        "The desired end state: component design, interaction patterns, "
                        "data flow, technology choices, and the design principles it embodies. "
                        "Include diagrams as ASCII art or structured descriptions.\n\n"
                        "## Architecture Decision Records (ADRs)\n"
                        "For each major decision: the options considered, the chosen approach, "
                        "and the rationale. Include trade-offs explicitly.\n\n"
                        "## Migration Strategy\n"
                        "How to move from current to target state safely:\n"
                        "- Strangler fig, big bang, or parallel run approach?\n"
                        "- Phased migration steps (what is done in this iteration vs later)\n"
                        "- Backward compatibility shims if needed during transition\n"
                        "- Data migration plan if schema changes are involved\n\n"
                        "## Implementation Plan\n"
                        "Ordered steps for this iteration: which files to create/modify, "
                        "which interfaces to define, which implementations to build, and "
                        "which old code to deprecate or remove.\n\n"
                        "## Invariants & Contracts\n"
                        "What must remain stable: public interfaces, data contracts, "
                        "behavior guarantees that existing consumers depend on.\n\n"
                        "## Testing Strategy\n"
                        "How to verify correctness at each migration step. What tests to "
                        "write before, during, and after the change.\n\n"
                        "## Rollback Plan\n"
                        "How to revert if the change causes problems: what to undo, "
                        "in what order, and how to verify rollback success.\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "Step-by-step implementation guide following the migration strategy, "
                        "exact interfaces to define, exact patterns to implement, and the "
                        "invariants to preserve throughout."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Developer implementing architecture",
            wave_type="execution",
            depends_on=("pm_plan", "tech_plan"),
            slots=(
                DagSlot(
                    slot_id="dev_impl",
                    label="Architecture Implementation",
                    is_lead=False,
                    suggested_specializations=(
                        "Backend Engineer", "Full-Stack Developer",
                        "Backend Developer", "Frontend Engineer",
                    ),
                    role_prompt=(
                        "You are the Developer implementing this architectural change. "
                        "The PM Lead has defined the business constraints and the Tech Lead "
                        "has designed the architecture and migration path. Your delegated "
                        "tasks are in each lead's 'Specialist Delegation > Developer' section.\n\n"
                        "Implement the architectural change with care:\n"
                        "- Follow the Tech Lead's migration steps in exact order\n"
                        "- Preserve all invariants and contracts specified\n"
                        "- Write tests before changing behavior (lock current behavior first)\n"
                        "- Respect the PM's business constraints at every step\n"
                        "- Implement backward compatibility shims if the Tech Lead specified them\n"
                        "- Document every ADR decision in code with comments\n"
                        "- Do not introduce new features — this is architecture only\n"
                        "- Design the rollback path as you implement (make each step revertible)\n\n"
                        "Use file_write for every file. Architecture changes touch many files — "
                        "be systematic, not opportunistic. If you discover the planned migration "
                        "has a flaw, document it clearly rather than improvising a different approach."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Tech Lead
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Tech Lead architecture review",
            wave_type="review",
            depends_on=("pm_plan", "tech_plan", "dev_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Architecture Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the architectural implementation "
                        "with the highest scrutiny — this change affects the whole system.\n\n"
                        "Evaluate:\n"
                        "- Architecture conformance: does the implementation reach the target state?\n"
                        "- ADR adherence: are all architectural decisions implemented as designed?\n"
                        "- Migration steps: were steps followed in order? Any skipped?\n"
                        "- Invariant preservation: are all contracts and public interfaces stable?\n"
                        "- Backward compatibility: do existing consumers still work?\n"
                        "- Test coverage: behavior locked before changes, migration verified\n"
                        "- Rollback feasibility: can each change be reverted safely?\n"
                        "- PM constraints: business constraints respected throughout?\n"
                        "- Code quality: new architecture is clean, consistent, and idiomatic\n"
                        "- Completeness: is the full migration done, or are there dangling old patterns?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Architecture Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, exact fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Developer\n"
                        "[Specific architectural corrections required]\n\n"
                        "Architecture changes have long-lived consequences. APPROVE only when "
                        "the target state is cleanly reached with no half-migrated patterns remaining."
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "The implementation reaches the target architecture state with no half-migrated patterns",
        "All architectural decisions (ADRs) are implemented exactly as designed",
        "Public interfaces and API contracts remain stable — no breaking changes to consumers",
        "Behavior-locking tests prove functional equivalence before and after the migration",
        "Each migration step can be independently reverted without data loss",
    ),
    validation_wave=DagWave(
        wave_number=0,
        label="Validating delegation plan",
        wave_type="validation",
        depends_on=("pm_plan", "tech_plan"),
        slots=(
            DagSlot(
                slot_id="delegation_check",
                label="Delegation Validation",
                is_lead=True,
                suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                role_prompt=(
                    "Review the delegation plans from the PM Lead and Tech Lead. "
                    "Architecture changes affect the whole system — verify that each "
                    "specialist's assignment has clear migration steps and no gaps."
                ),
            ),
        ),
    ),
    max_iterations=2,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Backend Engineer", "Full-Stack Developer",
        "Backend Developer", "Frontend Engineer",
    }),
)
