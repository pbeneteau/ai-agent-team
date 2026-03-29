"""DAG template: performance — profile and optimize a performance bottleneck.

Use when: the system is slow, a specific operation exceeds acceptable latency,
memory usage is excessive, or load testing has revealed bottlenecks.

Lead structure:
  Wave 1 (planning) — Tech Lead (profiling + optimization plan)
  Wave 2 (execution) — Developer
  Wave 3 (review)   — Tech Lead (verify gains, no regressions)
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

PERFORMANCE_TEMPLATE = DagTemplate(
    template_id="performance",
    name="Performance Optimization",
    description=(
        "Profile a performance problem and implement targeted optimizations. Use when "
        "the brief describes slow response times, high memory usage, excessive database "
        "queries, slow renders, or load test failures. The Tech Lead identifies the "
        "bottleneck and designs the optimization strategy before a developer implements."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: Tech Lead
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="Tech Lead profiling & planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Performance Plan",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. A performance problem has been identified. "
                        "Your job is to diagnose the bottleneck and produce a concrete "
                        "optimization plan that a developer can execute.\n\n"
                        "Produce the following sections:\n\n"
                        "## Performance Problem Statement\n"
                        "Precisely describe the issue: which operation is slow, what the "
                        "current latency/throughput is, what the target is, and under what "
                        "load conditions it occurs.\n\n"
                        "## Bottleneck Analysis\n"
                        "Root cause identification: where is time being spent? "
                        "Options: N+1 queries, missing indexes, unoptimized algorithms (O(n²)+), "
                        "excessive memory allocation, blocking I/O in async context, "
                        "unnecessary re-renders, large bundle sizes, missing caching, "
                        "serial work that could be parallel. Be specific — name the file "
                        "and function.\n\n"
                        "## Optimization Strategy\n"
                        "For each bottleneck: the specific optimization to apply and why it "
                        "will improve performance. Include expected improvement estimate.\n\n"
                        "## Implementation Plan\n"
                        "Ordered steps: which files to change, what to change, and what "
                        "pattern to use (e.g., add index on column X, convert loop to batch "
                        "query, memoize function Y, implement Redis cache for Z).\n\n"
                        "## Measurement Plan\n"
                        "How to verify the optimization worked: which benchmarks to run, "
                        "what metrics to measure before and after, and what the success "
                        "threshold is.\n\n"
                        "## Risk Assessment\n"
                        "Which optimizations trade correctness for speed and require extra "
                        "care (e.g., caching stale data, race conditions from parallelism). "
                        "How to mitigate each risk.\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "File-by-file optimization instructions, exact patterns to implement, "
                        "benchmarks to write, and correctness invariants to maintain."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Developer optimizing",
            wave_type="execution",
            depends_on=("tech_plan",),
            slots=(
                DagSlot(
                    slot_id="dev_impl",
                    label="Performance Optimization Implementation",
                    is_lead=False,
                    suggested_specializations=(
                        "Backend Engineer", "Frontend Engineer", "Full-Stack Developer",
                        "Backend Developer", "Frontend Developer",
                    ),
                    role_prompt=(
                        "You are the Developer implementing performance optimizations. "
                        "The Tech Lead has identified the bottlenecks and designed the "
                        "optimization strategy. Your delegated task is in the Tech Lead's "
                        "'Specialist Delegation > Developer' section.\n\n"
                        "Implement the optimizations precisely:\n"
                        "- Apply each optimization in the order the Tech Lead specified\n"
                        "- Write benchmark tests before and after each optimization\n"
                        "- Do not sacrifice correctness for speed — if an optimization "
                        "risks correctness, add guards and document the trade-off\n"
                        "- For caching: define TTL, cache invalidation strategy, and "
                        "what happens on cache miss\n"
                        "- For database: add indexes, optimize queries, add EXPLAIN ANALYZE "
                        "output as a comment to document the improvement\n"
                        "- For async: ensure no blocking calls in async code paths\n"
                        "- For frontend: verify bundle size, memoization correctness, "
                        "and no render cascades\n"
                        "- Add inline comments explaining each optimization and why it helps\n\n"
                        "Use file_write for every changed file. Include performance test "
                        "files that can be run to verify the improvement."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Tech Lead
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Tech Lead verifying performance",
            wave_type="review",
            depends_on=("tech_plan", "dev_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Performance Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Verify that the optimizations are correctly "
                        "implemented and that they address the bottlenecks you identified.\n\n"
                        "Evaluate:\n"
                        "- Bottleneck addressed: does each optimization target the right problem?\n"
                        "- Implementation correctness: are the optimizations applied correctly "
                        "without introducing correctness bugs?\n"
                        "- Completeness: all specified optimizations implemented?\n"
                        "- Measurement: are benchmarks present to verify improvement?\n"
                        "- Risk mitigations: are the risk controls for unsafe optimizations in place?\n"
                        "- Regression safety: does the code still behave correctly under all scenarios?\n"
                        "- Code quality: are optimizations readable and maintainable, not just fast?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Developer\n"
                        "[What to correct]\n\n"
                        "APPROVE when optimizations are correctly implemented and benchmarks "
                        "demonstrate improvement without regressions."
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "Each optimization targets the correct bottleneck identified in the profiling plan",
        "Optimizations do not introduce correctness bugs or change observable behavior",
        "Benchmarks or measurements are present demonstrating the improvement",
        "Risk mitigations for unsafe optimizations (caching, denormalization) are in place",
    ),
    max_iterations=2,
    required_roles=frozenset({
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Backend Engineer", "Frontend Engineer", "Full-Stack Developer",
        "Backend Developer", "Frontend Developer",
    }),
)
