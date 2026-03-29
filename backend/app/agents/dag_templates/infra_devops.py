"""DAG template: infra_devops — infrastructure, CI/CD, or DevOps work.

Use when: setting up or changing infrastructure, CI/CD pipelines, deployment
configuration, containerization, cloud resources, or operational tooling.

Lead structure:
  Wave 1 (planning) — DevOps Lead + Tech Lead in parallel
  Wave 2 (execution) — DevOps Engineer
  Wave 3 (review)   — DevOps Lead + Tech Lead in parallel
"""

from app.agents.dag_templates.schema import DagSlot, DagTemplate, DagWave

INFRA_DEVOPS_TEMPLATE = DagTemplate(
    template_id="infra_devops",
    name="Infrastructure & DevOps",
    description=(
        "Set up or change infrastructure, CI/CD pipelines, deployment configuration, "
        "containerization, cloud resources, monitoring, or operational tooling. Use when "
        "the brief involves Dockerfile changes, Kubernetes configs, Terraform/IaC, GitHub "
        "Actions, environment setup, or any infrastructure-as-code work. The DevOps Lead "
        "designs the infrastructure and the Tech Lead ensures application alignment."
    ),
    artifact_type="code",
    waves=(
        # ------------------------------------------------------------------
        # Wave 1 — Planning: DevOps Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=1,
            label="DevOps & Tech leads planning",
            wave_type="planning",
            depends_on=(),
            slots=(
                DagSlot(
                    slot_id="devops_plan",
                    label="DevOps Lead Infrastructure Plan",
                    is_lead=True,
                    suggested_specializations=("DevOps Lead", "Platform Lead", "Infrastructure Lead", "SRE Lead"),
                    role_prompt=(
                        "You are the DevOps Lead. Design the complete infrastructure solution "
                        "for this work.\n\n"
                        "Produce the following sections:\n\n"
                        "## Infrastructure Overview\n"
                        "What is being built or changed: services, environments, cloud resources, "
                        "networking, and how it fits the existing infrastructure.\n\n"
                        "## Architecture Design\n"
                        "Detailed design: resource topology, networking (VPCs, subnets, security "
                        "groups, load balancers), storage (volumes, buckets, databases), compute "
                        "(instances, containers, serverless), and service dependencies.\n\n"
                        "## Configuration Specifications\n"
                        "For each component: exact configuration values, environment variables, "
                        "resource sizing (CPU, memory, replicas), and health check definitions.\n\n"
                        "## CI/CD Pipeline Design (if applicable)\n"
                        "Pipeline stages, triggers, environment promotion strategy, rollback "
                        "mechanism, secrets management, and artifact storage.\n\n"
                        "## Security & Compliance\n"
                        "IAM roles and policies (least privilege), network isolation, secrets "
                        "management (no hardcoded credentials), encryption at rest and in transit.\n\n"
                        "## Observability\n"
                        "Metrics, logging, alerting, and tracing setup. What to monitor and "
                        "what thresholds to alert on.\n\n"
                        "## Rollout & Rollback Strategy\n"
                        "How to deploy safely: phased rollout, feature flags, blue/green, "
                        "canary. How to roll back if something goes wrong.\n\n"
                        "## Specialist Delegation\n"
                        "### DevOps Engineer\n"
                        "File-by-file implementation guide: which files to create/modify, "
                        "exact configuration values, and the deployment sequence to follow."
                    ),
                ),
                DagSlot(
                    slot_id="tech_plan",
                    label="Tech Lead Application Alignment",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the infrastructure requirements from "
                        "an application perspective and define how the application must adapt.\n\n"
                        "Produce the following sections:\n\n"
                        "## Application-Infrastructure Contract\n"
                        "What the application expects from the infrastructure: environment "
                        "variable names, service discovery patterns, secrets access, port "
                        "bindings, and health check endpoints.\n\n"
                        "## Application Changes Required\n"
                        "What application code must change to work with the new infrastructure: "
                        "config file updates, connection string changes, graceful shutdown "
                        "handlers, readiness/liveness probe endpoints.\n\n"
                        "## Environment Parity\n"
                        "How to ensure dev/staging/prod environments are consistent. "
                        "What must be identical vs what can differ.\n\n"
                        "## Risk Assessment\n"
                        "What could go wrong during deployment? Downtime risks, data migration "
                        "risks, dependency version conflicts.\n\n"
                        "## Specialist Delegation\n"
                        "### DevOps Engineer\n"
                        "Application-side configuration requirements and any application code "
                        "changes needed alongside the infrastructure work."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 2 — Execution: DevOps Engineer
        # ------------------------------------------------------------------
        DagWave(
            wave_number=2,
            label="DevOps Engineer implementing",
            wave_type="execution",
            depends_on=("devops_plan", "tech_plan"),
            slots=(
                DagSlot(
                    slot_id="devops_impl",
                    label="Infrastructure Implementation",
                    is_lead=False,
                    suggested_specializations=("DevOps Engineer", "Platform Engineer", "SRE", "Infrastructure Engineer"),
                    role_prompt=(
                        "You are the DevOps Engineer. The DevOps Lead has designed the "
                        "infrastructure and the Tech Lead has defined the application alignment. "
                        "Your delegated tasks are in each lead's 'Specialist Delegation > "
                        "DevOps Engineer' section.\n\n"
                        "Implement the complete infrastructure:\n"
                        "- Create/modify all infrastructure files (Dockerfile, docker-compose, "
                        "  Kubernetes manifests, Terraform, CI/CD pipelines, etc.)\n"
                        "- Follow the DevOps Lead's architecture design exactly\n"
                        "- Implement all security controls: least-privilege IAM, network isolation, "
                        "  secrets management (never hardcode credentials)\n"
                        "- Implement observability: logging config, metrics endpoints, alerts\n"
                        "- Implement health checks and graceful shutdown per the Tech Lead's spec\n"
                        "- Write runbook comments in configuration files for non-obvious settings\n"
                        "- Validate that environment variables align with the application contract\n\n"
                        "Use file_write for every file. Include a deployment README with "
                        "the exact steps to apply this infrastructure change and how to roll back."
                    ),
                ),
            ),
        ),
        # ------------------------------------------------------------------
        # Wave 3 — Review: DevOps Lead + Tech Lead (parallel)
        # ------------------------------------------------------------------
        DagWave(
            wave_number=3,
            label="DevOps & Tech review",
            wave_type="review",
            depends_on=("devops_plan", "tech_plan", "devops_impl"),
            slots=(
                DagSlot(
                    slot_id="devops_review",
                    label="DevOps Lead Review",
                    is_lead=True,
                    suggested_specializations=("DevOps Lead", "Platform Lead", "Infrastructure Lead", "SRE Lead"),
                    role_prompt=(
                        "You are the DevOps Lead. Review the infrastructure implementation "
                        "against your design.\n\n"
                        "Evaluate:\n"
                        "- Architecture conformance: does implementation match your design?\n"
                        "- Security: least-privilege IAM, no hardcoded secrets, network isolation\n"
                        "- Observability: metrics, logging, and alerting correctly configured\n"
                        "- Rollout safety: rollback mechanism is present and correct\n"
                        "- Environment consistency: dev/staging/prod parity maintained\n"
                        "- Resource sizing: CPU, memory, replica counts appropriate\n"
                        "- CI/CD pipeline: stages, gates, and artifact management correct\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### DevOps Engineer\n"
                        "[Infrastructure corrections required]"
                    ),
                ),
                DagSlot(
                    slot_id="tech_review",
                    label="Tech Lead Application Review",
                    is_lead=True,
                    suggested_specializations=("Tech Lead", "Engineering Manager", "Senior Engineer"),
                    role_prompt=(
                        "You are the Tech Lead. Review the infrastructure implementation "
                        "from the application's perspective.\n\n"
                        "Evaluate:\n"
                        "- Application contract: do env vars, ports, and service names match?\n"
                        "- Health checks: readiness and liveness endpoints correct?\n"
                        "- Graceful shutdown: proper signal handling implemented?\n"
                        "- Application changes: are required application-side changes included?\n"
                        "- Environment parity: will the application behave consistently across envs?\n\n"
                        "Output your decision in this exact format:\n\n"
                        "## Review Decision\n"
                        "**Decision:** [APPROVE | MINOR_FIX | REVISE]\n\n"
                        "## Evaluation\n"
                        "[Detailed evaluation per area]\n\n"
                        "## Issues (if MINOR_FIX or REVISE)\n"
                        "[Each issue: file, description, fix required]\n\n"
                        "## Specialist Feedback (if REVISE)\n"
                        "### DevOps Engineer\n"
                        "[Application alignment corrections required]"
                    ),
                ),
            ),
        ),
    ),
    needs_compile=False,
    compile_slot=None,
    review_criteria=(
        "Infrastructure configuration matches the design with no hardcoded secrets",
        "Rollback mechanism is present and documented for every deployment change",
        "Health checks, readiness probes, and observability are correctly configured",
        "Environment parity is maintained — dev, staging, and production behave consistently",
    ),
    max_iterations=2,
    required_roles=frozenset({
        "DevOps Lead", "Platform Lead", "Infrastructure Lead", "SRE Lead",
        "Tech Lead", "Engineering Manager", "Senior Engineer",
        "DevOps Engineer", "Platform Engineer", "SRE", "Infrastructure Engineer",
    }),
)
