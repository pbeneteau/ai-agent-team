"""DAG template: api_integration — integrate a third-party or internal API.

Use when: connecting to an external service (payment, auth, messaging, maps,
AI, etc.) or integrating a new internal service into the application.

Lead structure:
  Wave 1 (planning) — PM Lead + Tech Lead in parallel
  Wave 2 (execution) — Backend Developer
  Wave 3 (review)   — Tech Lead
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

API_INTEGRATION_TEMPLATE = DagTemplate(
    template_id="api_integration",
    name="API Integration",
    description=(
        "Integrate a third-party API (payment processor, auth provider, email service, "
        "maps, AI, etc.) or connect to a new internal service. Use when the brief requires "
        "consuming an external or internal API that is not yet integrated. The PM Lead "
        "defines the integration contract and the Tech Lead designs the integration "
        "architecture including auth, error handling, and resilience patterns."
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
                    label="PM Lead Integration Requirements",
                    is_lead=True,
                    suggested_specializations=("Product Manager", "Product Lead", "PM"),
                    role_prompt=(
                        "You are the Product Manager lead for this API integration. Define "
                        "the complete product requirements and the integration contract.\n\n"
                        "Produce the following sections:\n\n"
                        "## Integration Purpose\n"
                        "Why is this integration being built? What user capability or "
                        "business process does it enable?\n\n"
                        "## Integration Scope\n"
                        "Which features of the third-party API are being used (not all "
                        "endpoints — only what is needed now). Out-of-scope endpoints to "
                        "explicitly exclude.\n\n"
                        "## Functional Requirements\n"
                        "Every behavior the integration must provide: which operations to "
                        "support, data to exchange, transformations to apply, and how "
                        "results are surfaced to users or other systems.\n\n"
                        "## Error Handling Requirements\n"
                        "User-facing behavior for each failure scenario: API down, "
                        "rate limited, invalid credentials, rejected request, timeout. "
                        "What the user sees and what the system does in each case.\n\n"
                        "## Acceptance Criteria\n"
                        "Given/When/Then for every integration scenario including failures.\n\n"
                        "## Specialist Delegation\n"
                        "### Backend Developer\n"
                        "Which API operations to integrate, data transformation requirements, "
                        "error handling UX, and all acceptance criteria to satisfy."
                    ),
                ),
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Integration Architecture",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Design the complete technical architecture "
                        "for this API integration.\n\n"
                        "Produce the following sections:\n\n"
                        "## Integration Architecture\n"
                        "How the integration fits into the system: which layer handles it "
                        "(service layer, adapter, client library), how it is called from "
                        "business logic, and how responses are mapped to domain models.\n\n"
                        "## Authentication & Credentials\n"
                        "Auth mechanism (API key, OAuth2, JWT, HMAC, etc.). How credentials "
                        "are stored (env vars, secrets manager) and how they are loaded at "
                        "runtime. Token refresh strategy if applicable.\n\n"
                        "## Client Design\n"
                        "The API client class/module structure: base URL configuration, "
                        "request/response serialization, header management, and shared "
                        "error parsing.\n\n"
                        "## Resilience Patterns\n"
                        "Timeout values (connect + read), retry strategy (max attempts, "
                        "backoff, which errors are retryable), circuit breaker configuration, "
                        "and fallback behavior when the API is unavailable.\n\n"
                        "## Webhook Handling (if applicable)\n"
                        "Endpoint design, signature verification, idempotency key handling, "
                        "event processing strategy (sync vs async queue).\n\n"
                        "## Rate Limiting\n"
                        "The third-party's rate limits. How to stay within them: request "
                        "queuing, throttling, and backpressure strategy.\n\n"
                        "## Testing Strategy\n"
                        "How to test without hitting the live API: mock/stub approach, "
                        "recorded fixtures, or sandbox environment. Which integration tests "
                        "must run against the real API (and how to gate them).\n\n"
                        "## Observability\n"
                        "What to log (request/response summaries, latency, error codes), "
                        "what metrics to expose, and what to alert on.\n\n"
                        "## Specialist Delegation\n"
                        "### Backend Developer\n"
                        "Step-by-step implementation guide: file structure, class design, "
                        "exact patterns to use for auth/retry/errors, and tests to write."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Backend Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Backend Developer implementing",
            wave_type="execution",
            depends_on=("pm_plan", "tech_plan"),
            slots=(
                DagSlot(
                    slot_id="backend_impl",
                    label="Integration Implementation",
                    is_lead=False,
                    suggested_specializations=("Backend Engineer", "Backend Developer", "Full-Stack Developer"),
                    role_prompt=(
                        "You are the Backend Developer building this API integration. "
                        "The PM Lead has defined the integration contract and the Tech Lead "
                        "has designed the architecture. Your delegated tasks are in each "
                        "lead's 'Specialist Delegation > Backend Developer' section.\n\n"
                        "Implement the complete integration:\n"
                        "- Build the API client per the Tech Lead's design\n"
                        "- Implement auth with credentials from environment variables only\n"
                        "- Implement all resilience patterns: timeouts, retries, circuit breaker\n"
                        "- Map all third-party responses to internal domain models\n"
                        "- Handle every error case per the PM's requirements\n"
                        "- Implement webhook endpoint and signature verification if specified\n"
                        "- Add structured logging for all API calls (latency, status, errors)\n"
                        "- Write tests using the mock/stub approach the Tech Lead specified\n"
                        "- Never log API keys, tokens, or sensitive request/response data\n\n"
                        "Use file_write for every file. The client must be isolated enough "
                        "to swap the third-party provider without touching business logic. "
                        "Document rate limits and any third-party API quirks with comments."
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
            depends_on=("pm_plan", "tech_plan", "backend_impl"),
            slots=(
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the API integration implementation.\n\n"
                        "Evaluate:\n"
                        "- Architecture: does the implementation match your client design?\n"
                        "- Auth security: credentials from env only, no hardcoded secrets\n"
                        "- Resilience: timeouts, retries, circuit breaker all implemented?\n"
                        "- Error handling: all PM-specified failure scenarios handled correctly?\n"
                        "- Provider isolation: is the client properly abstracted?\n"
                        "- Observability: request logging and metrics in place?\n"
                        "- Test coverage: mocks/stubs correct, all error paths tested?\n"
                        "- Security: no sensitive data in logs, webhook signatures verified\n"
                        "- PM contract: all integration scenarios satisfy acceptance criteria\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Backend Developer\n"
                        "[Corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "API credentials are loaded from environment variables — no hardcoded secrets",
        "Resilience patterns (timeouts, retries, circuit breaker) are implemented correctly",
        "All error scenarios from the PM spec are handled with appropriate fallbacks",
        "The external API client is properly abstracted behind an interface for testability",
        "Webhook signature verification is implemented if the integration receives callbacks",
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
                    "API integrations involve external contracts — verify that auth "
                    "flows, error handling, and data mapping are fully specified."
                ),
            ),
        ),
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Product Manager", "Product Lead", "PM",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Backend Engineer", "Backend Developer", "Full-Stack Developer",
    }),
)
