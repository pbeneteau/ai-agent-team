"""
Pre-execution cost estimator.

Estimates token usage and USD cost before a task runs, based on the
execution plan structure and historical heuristics per node type.
"""
from app.config.pricing import ANTHROPIC_PRICING_USD_PER_MILLION
from app.models.task import TaskExecutionPlan, TaskNodeType

# Heuristic (input_tokens, output_tokens) per node type for Sonnet tier
_NODE_HEURISTICS: dict[str, tuple[int, int]] = {
    TaskNodeType.SPECIALIST.value: (3_000, 4_000),
    TaskNodeType.LEAD_COMPILE.value: (5_000, 6_000),
    TaskNodeType.SINGLE_AGENT.value: (3_000, 4_000),
}

# Extra input tokens per specialist result absorbed by the lead compiler
_LEAD_COMPILE_EXTRA_PER_SPECIALIST = 1_000

# Opus tier multiplier (Opus is roughly 1.67× more expensive than Sonnet)
_OPUS_COST_MULTIPLIER = 1.67


def _compute_cost(model_key: str, input_tokens: int, output_tokens: int) -> float:
    pricing = ANTHROPIC_PRICING_USD_PER_MILLION.get(
        model_key, ANTHROPIC_PRICING_USD_PER_MILLION["_default"]
    )
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def estimate_task_cost(
    plan: TaskExecutionPlan,
    model_key: str = "_default",
) -> tuple[int, int, float]:
    """
    Return (estimated_input_tokens, estimated_output_tokens, estimated_cost_usd).

    Heuristics per node type (Sonnet tier):
    - SPECIALIST    : ~3 000 input  + ~4 000 output
    - LEAD_COMPILE  : ~5 000 input  + ~6 000 output
                      (+ 1 000 input per specialist in the plan)
    - SINGLE_AGENT  : ~3 000 input  + ~4 000 output

    Pass model_key="claude-opus-4-5" for Opus-tier tasks; the function
    applies the correct per-million pricing automatically.
    """
    specialist_count = sum(
        1 for n in plan.nodes if n.node_type == TaskNodeType.SPECIALIST
    )

    total_input = 0
    total_output = 0

    for node in plan.nodes:
        node_type_val = (
            node.node_type.value
            if hasattr(node.node_type, "value")
            else str(node.node_type)
        )
        base_input, base_output = _NODE_HEURISTICS.get(node_type_val, (3_000, 4_000))

        # Lead compiler gets all specialist outputs as context
        if node_type_val == TaskNodeType.LEAD_COMPILE.value:
            base_input += specialist_count * _LEAD_COMPILE_EXTRA_PER_SPECIALIST

        total_input += base_input
        total_output += base_output

    cost = _compute_cost(model_key, total_input, total_output)
    return total_input, total_output, round(cost, 4)
