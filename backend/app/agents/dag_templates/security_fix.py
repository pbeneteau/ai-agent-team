"""DAG template: security_fix — address a security vulnerability.

Use when: a security issue has been identified — vulnerability, auth bypass,
data exposure, injection risk, or failed security audit finding.

Lead structure:
  Wave 1 (planning) — Security Lead + Tech Lead in parallel
  Wave 2 (execution) — Developer
  Wave 3 (review)   — Security Lead + Tech Lead in parallel
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

SECURITY_FIX_TEMPLATE = DagTemplate(
    template_id="security_fix",
    name="Security Fix",
    description=(
        "Address a security vulnerability, auth bypass, data exposure risk, injection "
        "flaw, or security audit finding. Use when the brief describes a security issue "
        "that must be fixed with careful threat modeling. The Security Lead assesses the "
        "threat and defines the security requirements; the Tech Lead designs the technical "
        "fix. Both review the implementation before approval."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: Security Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="Security & Tech leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="security_plan",
                    label="Security Lead Threat Assessment",
                    is_lead=True,
                    suggested_specializations=("Security Lead", "Security Engineer", "AppSec Lead"),
                    role_prompt=(
                        "You are the Security Lead. A security issue has been identified. "
                        "Produce a complete threat assessment and security requirements "
                        "that will govern the fix.\n\n"
                        "Produce the following sections:\n\n"
                        "## Vulnerability Classification\n"
                        "Type of vulnerability (OWASP category, CWE ID if known), severity "
                        "(Critical/High/Medium/Low), and CVSS score estimate with justification.\n\n"
                        "## Threat Model\n"
                        "Who is the attacker? What is their access level? What is the attack "
                        "vector (network, local, adjacent)? What privileges are required? "
                        "What is the impact if exploited (confidentiality, integrity, availability)?\n\n"
                        "## Attack Scenarios\n"
                        "Concrete, step-by-step descriptions of how this vulnerability can be "
                        "exploited. Include the exact payload or technique for each scenario.\n\n"
                        "## Affected Components\n"
                        "Every file, endpoint, service, and data asset that is vulnerable or "
                        "at risk. Map attack paths through the system.\n\n"
                        "## Security Requirements for the Fix\n"
                        "What the fix MUST achieve from a security standpoint. Expressed as "
                        "security invariants: 'The system must never allow X', "
                        "'All inputs must be Y before reaching Z'.\n\n"
                        "## Verification Criteria\n"
                        "How to confirm the vulnerability is closed: specific test cases, "
                        "payloads to reject, and behaviors to verify.\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "Security constraints the fix must enforce, attack scenarios it must "
                        "prevent, and verification tests to write."
                    ),
                ),
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Fix Design",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. A security vulnerability has been identified. "
                        "Design the technical implementation of the fix based on the security "
                        "assessment.\n\n"
                        "Produce the following sections:\n\n"
                        "## Fix Architecture\n"
                        "The technical approach to closing the vulnerability: what changes "
                        "at which layer (input validation, auth middleware, data access, "
                        "output encoding), and why this approach is correct and complete.\n\n"
                        "## Implementation Plan\n"
                        "Ordered steps to implement the fix. For each step: file to change, "
                        "function to modify, and exact logic to add or change.\n\n"
                        "## Defense in Depth\n"
                        "Beyond the primary fix: additional mitigations to add (rate limiting, "
                        "logging, alerts, additional validation layers) to make exploitation "
                        "harder even if the primary fix has gaps.\n\n"
                        "## Backward Compatibility\n"
                        "Does the fix break any existing valid functionality? If so, how to "
                        "handle the migration (e.g., deprecation period, client updates needed).\n\n"
                        "## Regression Risk\n"
                        "What working functionality could break? What to verify after the fix.\n\n"
                        "## Specialist Delegation\n"
                        "### Developer\n"
                        "File-by-file implementation instructions, exact code patterns to use "
                        "(e.g., which sanitization library, which auth pattern), and the "
                        "complete test suite to write including attack payload tests."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: Developer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="Developer implementing fix",
            wave_type="execution",
            depends_on=("security_plan", "tech_plan"),
            slots=(
                DagSlot(
                    slot_id="dev_impl",
                    label="Security Fix Implementation",
                    is_lead=False,
                    suggested_specializations=(
                        "Backend Engineer", "Security Engineer", "Backend Developer",
                        "Full-Stack Developer",
                    ),
                    role_prompt=(
                        "You are the Developer implementing this security fix. The Security "
                        "Lead has defined the threat model and security requirements. The "
                        "Tech Lead has designed the fix architecture. Your delegated tasks "
                        "are in each lead's 'Specialist Delegation > Developer' section.\n\n"
                        "Implement the fix with zero shortcuts:\n"
                        "- Follow the Tech Lead's implementation plan exactly\n"
                        "- Satisfy every security requirement from the Security Lead\n"
                        "- Implement all defense-in-depth mitigations the Tech Lead specified\n"
                        "- Write tests for every attack scenario described by the Security Lead\n"
                        "- Verify that valid legitimate use cases still work\n"
                        "- Add security-relevant logging (failed auth, rejected inputs, anomalies)\n"
                        "- Never leave a partial fix — all attack vectors must be closed\n"
                        "- Do not log sensitive data (passwords, tokens, PII)\n\n"
                        "Use file_write for every file. Security fixes must be thorough — "
                        "a partial fix is worse than no fix because it creates false confidence. "
                        "Document each security decision with an inline comment referencing "
                        "the threat it mitigates."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: Security Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="Security & Tech review",
            wave_type="review",
            depends_on=("security_plan", "tech_plan", "dev_impl"),
            slots=(
                DagSlot(
                    slot_id="security_review",
                    label="Security Lead Review",
                    is_lead=True,
                    suggested_specializations=("Security Lead", "Security Engineer", "AppSec Lead"),
                    role_prompt=(
                        "You are the Security Lead. Verify that the fix closes the "
                        "vulnerability completely and satisfies all security requirements.\n\n"
                        "Evaluate:\n"
                        "- Vulnerability closed: does the fix prevent all attack scenarios you described?\n"
                        "- Security requirements: are all your security invariants enforced?\n"
                        "- Attack tests: are tests present for each attack payload?\n"
                        "- Defense in depth: are the additional mitigations implemented?\n"
                        "- No new vulnerabilities: does the fix introduce any new security issues?\n"
                        "- Sensitive data: is PII, tokens, or credentials handled correctly?\n"
                        "- Logging: are security events logged appropriately without leaking data?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Security Evaluation\n"
                        "[Detailed evaluation of each attack scenario and security requirement]\n\n"
                        "## Remaining Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: attack vector still open, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Developer\n"
                        "[Specific security gaps to close]\n\n"
                        "APPROVE only when all attack scenarios are provably prevented. "
                        "Security is binary — partial approval is not an option."
                    ),
                ),
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the security fix for technical "
                        "correctness and regression safety.\n\n"
                        "Evaluate:\n"
                        "- Fix architecture: was your design implemented correctly?\n"
                        "- Completeness: all files and layers changed as specified?\n"
                        "- Regression safety: does legitimate functionality still work?\n"
                        "- Code quality: is the fix clean, readable, and maintainable?\n"
                        "- Test coverage: are both security tests and regression tests present?\n"
                        "- Performance: does the fix introduce unacceptable latency?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Technical Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### Developer\n"
                        "[Technical corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "The vulnerability is fully mitigated — all identified attack vectors are blocked",
        "Fix does not introduce new attack surfaces or weaken existing defenses",
        "Input validation is applied at every entry point handling untrusted data",
        "Secrets, tokens, and credentials are not exposed in code, logs, or error messages",
        "Security-specific tests exercise each attack payload from the threat model",
    ),
    max_iterations=3,
    required_roles=frozenset({
        "Security Lead", "Security Engineer", "AppSec Lead",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "Backend Engineer", "Backend Developer", "Full-Stack Developer",
    }),
)
