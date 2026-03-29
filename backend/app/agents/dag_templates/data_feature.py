"""DAG template: data_feature — data pipeline, analytics, or data-intensive feature.

Use when: building data pipelines, ETL processes, analytics dashboards, reporting
features, ML model integrations, or any feature where data modeling and data
quality are the primary concerns.

Lead structure:
  Wave 1 (planning) — PM Lead + Data Lead in parallel
  Wave 2 (execution) — Data Engineer + Backend Developer in parallel
  Wave 3 (review)   — Data Lead + Tech Lead in parallel
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

DATA_FEATURE_TEMPLATE = DagTemplate(
    template_id="data_feature",
    name="Data Feature",
    description=(
        "Build a data pipeline, analytics feature, reporting system, ETL process, or "
        "any feature where data modeling and data quality are primary concerns. Use when "
        "the brief involves processing, transforming, storing, or visualizing data at "
        "scale. The PM Lead defines the data requirements and the Data Lead designs the "
        "data model and pipeline architecture."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: PM Lead + Data Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="PM & Data leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="pm_plan",
                    label="PM Lead Data Requirements",
                    is_lead=True,
                    suggested_specializations=("Product Manager", "Product Lead", "PM"),
                    role_prompt=(
                        "You are the Product Manager lead for this data feature. Define "
                        "the complete data requirements from a product and business perspective.\n\n"
                        "Produce the following sections:\n\n"
                        "## Business Problem\n"
                        "What business question or operational need does this data feature "
                        "address? Who consumes the data and how do they use it?\n\n"
                        "## Data Requirements\n"
                        "What data must be collected, processed, or exposed:\n"
                        "- Input data sources (databases, APIs, files, streams, events)\n"
                        "- Output data consumers (dashboards, APIs, reports, ML models)\n"
                        "- Data freshness requirements (real-time, near-real-time, batch)\n"
                        "- Data retention policy (how long to keep data, archival rules)\n\n"
                        "## Functional Requirements\n"
                        "Every behavior the feature must have: data transformations, "
                        "aggregations, filtering, enrichment, deduplication, and "
                        "error/outlier handling rules.\n\n"
                        "## Data Quality Requirements\n"
                        "Completeness, accuracy, timeliness, and consistency requirements. "
                        "What constitutes a data quality failure and how it should be handled.\n\n"
                        "## Acceptance Criteria\n"
                        "Given/When/Then statements: specific data scenarios, volume ranges, "
                        "and expected output for each.\n\n"
                        "## Specialist Delegation\n"
                        "### Data Engineer\n"
                        "Data sources, transformations, output format, freshness requirements, "
                        "and data quality rules to implement.\n\n"
                        "### Backend Developer\n"
                        "API endpoints or data access layer needed to expose the processed "
                        "data to consumers."
                    ),
                ),
                DagSlot(
                    slot_id="data_plan",
                    label="Data Lead Architecture",
                    is_lead=True,
                    suggested_specializations=("Data Lead", "Data Architect", "Analytics Lead", "Data Engineering Lead"),
                    role_prompt=(
                        "You are the Data Lead. Design the complete data architecture for "
                        "this feature.\n\n"
                        "Produce the following sections:\n\n"
                        "## Data Model\n"
                        "Schema design for all new tables, views, or data structures: "
                        "column names, types, constraints, indexes, and partitioning strategy. "
                        "Justify each design decision (normalization vs denormalization, "
                        "column types, index choices).\n\n"
                        "## Pipeline Architecture\n"
                        "End-to-end data flow: ingestion → transformation → storage → serving. "
                        "Which processing framework (batch vs stream), orchestration approach, "
                        "and intermediate storage layers.\n\n"
                        "## Transformation Logic\n"
                        "Each transformation step: input schema, transformation rules, output "
                        "schema, and business logic applied. Handle edge cases explicitly "
                        "(nulls, duplicates, out-of-range values, late-arriving data).\n\n"
                        "## Performance & Scalability\n"
                        "Expected data volumes and velocity. Query optimization strategy: "
                        "partitioning, clustering, materialized views, caching layers. "
                        "Estimated query latency targets.\n\n"
                        "## Data Quality Framework\n"
                        "Validation checks to run: schema validation, null checks, range checks, "
                        "referential integrity, duplicate detection. What happens when a check fails.\n\n"
                        "## Lineage & Observability\n"
                        "How to track data lineage, monitor pipeline health, and alert on failures. "
                        "Key metrics: rows processed, error rates, latency, freshness lag.\n\n"
                        "## Specialist Delegation\n"
                        "### Data Engineer\n"
                        "Exact schema DDL, pipeline implementation steps, transformation logic, "
                        "and data quality checks to build.\n\n"
                        "### Backend Developer\n"
                        "Data access layer design: query patterns, caching strategy, and "
                        "API response schemas for serving the processed data."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Data Engineer + Backend Developer (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Data & Backend building",
            wave_type="execution",
            depends_on=("pm_plan", "data_plan"),
            slots=(
                DagSlot(
                    slot_id="data_impl",
                    label="Data Engineering Implementation",
                    is_lead=False,
                    suggested_specializations=("Data Engineer", "Analytics Engineer", "Data Developer"),
                    role_prompt=(
                        "You are the Data Engineer. The PM Lead has defined the data requirements "
                        "and the Data Lead has designed the architecture. Your delegated tasks "
                        "are in each lead's 'Specialist Delegation > Data Engineer' section.\n\n"
                        "Implement the complete data pipeline:\n"
                        "- Create all database migrations per the Data Lead's schema design\n"
                        "- Implement all transformation logic exactly as specified\n"
                        "- Implement all data quality checks with proper failure handling\n"
                        "- Build pipeline orchestration (scheduling, retries, alerting)\n"
                        "- Handle all edge cases: nulls, duplicates, out-of-order data, "
                        "  schema drift, upstream failures\n"
                        "- Implement observability: row counts, error rates, freshness metrics\n"
                        "- Write tests with representative data including edge case datasets\n\n"
                        "Use file_write for every file. Data bugs are silent and destructive — "
                        "test with realistic data volumes and edge cases. Document every "
                        "transformation decision with an inline comment."
                    ),
                ),
                DagSlot(
                    slot_id="backend_impl",
                    label="Backend Data API Implementation",
                    is_lead=False,
                    suggested_specializations=("Backend Engineer", "Backend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Backend Developer building the data serving layer. "
                        "Your delegated task is in each lead's 'Specialist Delegation > "
                        "Backend Developer' section.\n\n"
                        "Implement the data access and serving layer:\n"
                        "- Build all API endpoints for serving processed data to consumers\n"
                        "- Implement query optimization per the Data Lead's strategy\n"
                        "- Implement caching where specified (cache keys, TTL, invalidation)\n"
                        "- Handle large result sets with pagination\n"
                        "- Validate query parameters and return clear error messages\n"
                        "- Write integration tests with realistic data\n\n"
                        "Use file_write for every file. Data APIs must handle large volumes "
                        "gracefully — always paginate, never return unbounded result sets."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Data Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Data & Tech review",
            wave_type="review",
            depends_on=("pm_plan", "data_plan", "data_impl", "backend_impl"),
            slots=(
                DagSlot(
                    slot_id="data_review",
                    label="Data Lead Review",
                    is_lead=True,
                    suggested_specializations=("Data Lead", "Data Architect", "Analytics Lead", "Data Engineering Lead"),
                    role_prompt=(
                        "You are the Data Lead. Review the data pipeline implementation "
                        "against your architecture design.\n\n"
                        "Evaluate:\n"
                        "- Schema correctness: does the DDL match your design exactly?\n"
                        "- Transformation fidelity: is the business logic implemented correctly?\n"
                        "- Edge case handling: are nulls, duplicates, and late data handled?\n"
                        "- Data quality checks: all validations implemented and tested?\n"
                        "- Performance: query plans efficient? Indexes used correctly?\n"
                        "- Observability: pipeline metrics and freshness monitoring present?\n"
                        "- PM requirements: are all data quality and freshness requirements met?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Data Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file/table, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Data Engineer\n"
                        "[Data pipeline corrections required]"
                    ),
                ),
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Code Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the backend API and overall code "
                        "quality of the data feature.\n\n"
                        "Evaluate:\n"
                        "- API design: endpoints correct, response schemas match PM contract\n"
                        "- Code quality: readable, maintainable, follows project conventions\n"
                        "- Error handling: all failure modes handled gracefully\n"
                        "- Performance: no unbounded queries, pagination enforced, caching correct\n"
                        "- Security: no data leakage, proper auth, input validation\n"
                        "- Test coverage: realistic test data, edge cases covered\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Technical Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Backend Developer\n"
                        "[Backend corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "Schema DDL matches the data architecture design exactly",
        "Transformation logic handles nulls, duplicates, and late-arriving data correctly",
        "Data quality validations are implemented and tested with realistic edge cases",
        "Query performance is acceptable — appropriate indexes are used, no full table scans",
        "Pipeline observability (freshness monitoring, row count assertions) is in place",
    ),
    validation_wave=DagWave(
        wave_number=0,
        label="Validating delegation plan",
        wave_type="validation",
        depends_on=("pm_plan", "data_plan"),
        slots=(
            DagSlot(
                slot_id="delegation_check",
                label="Delegation Validation",
                is_lead=True,
                suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                role_prompt=(
                    "Review the delegation plans from the PM Lead and Data Lead. "
                    "Data features involve schema design and pipeline logic — verify "
                    "that data contracts, transformation rules, and quality checks "
                    "are fully specified for each specialist."
                ),
            ),
        ),
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Data Lead", "Data Architect", "Analytics Lead", "Data Engineering Lead",
        "Data Engineer", "Analytics Engineer", "Data Developer",
        "Backend Engineer", "Backend Developer", "Full-Stack Developer",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
    }),
)
