"""
Execution wave planner.

Given a set of queued tasks and their `blocks` relations, produces an
ordered list of parallel execution groups using a topological sort (Kahn's
algorithm).  Tasks with no blockers form group 1; tasks that depended on
group 1 form group 2, and so on.
"""
from __future__ import annotations

from typing import Any


def suggest_execution_wave(
    tasks: list[Any],
    relations: list[Any],
) -> dict[str, Any]:
    """
    Analyse queued tasks and suggest an optimal execution batch.

    Parameters
    ----------
    tasks:
        List of TaskResponse objects (must have .id, .estimated_cost_usd,
        .execution_plan.nodes).
    relations:
        List of TaskRelationResponse objects (must have .type,
        .source_task_id, .target_task_id).

    Returns
    -------
    {
        "parallel_groups": [[task_id, ...], ...],  # ordered parallel waves
        "total_estimated_cost_usd": float,
        "estimated_duration_minutes": float,
        "blocked_tasks": [{"task_id": str, "blocked_by": [str, ...]}, ...],
    }
    """
    task_map: dict[str, Any] = {t.id: t for t in tasks}

    # depends_on[tid] = set of task IDs that must finish before tid can run
    depends_on: dict[str, set[str]] = {tid: set() for tid in task_map}

    for rel in relations:
        if rel.type != "blocks":
            continue
        blocker_id = rel.source_task_id
        blocked_id = rel.target_task_id
        # Only consider intra-wave dependencies
        if blocker_id in task_map and blocked_id in task_map:
            depends_on[blocked_id].add(blocker_id)

    # Kahn's algorithm — assign each task to the earliest group where all
    # its dependencies are satisfied.
    groups: list[list[str]] = []
    completed: set[str] = set()
    remaining: set[str] = set(task_map.keys())
    blocked_tasks: list[dict[str, Any]] = []

    while remaining:
        ready = {
            tid
            for tid in remaining
            if all(dep in completed for dep in depends_on[tid])
        }
        if not ready:
            # Cycle or external dependency — collect remaining as blocked
            for tid in sorted(remaining):
                blocked_tasks.append(
                    {
                        "task_id": tid,
                        "blocked_by": sorted(depends_on[tid] - completed),
                    }
                )
            break

        groups.append(sorted(ready))
        completed.update(ready)
        remaining -= ready

    # Cost totals
    total_cost = sum(t.estimated_cost_usd or 0.0 for t in tasks)

    # Duration estimate: sum of per-group maxima (groups run serially,
    # tasks within a group run in parallel). ~3 min per node as a baseline.
    _MINUTES_PER_NODE = 3.0
    estimated_duration = sum(
        max(
            (len(task_map[tid].execution_plan.nodes) for tid in group),
            default=1,
        )
        * _MINUTES_PER_NODE
        for group in groups
    )

    return {
        "parallel_groups": groups,
        "total_estimated_cost_usd": round(total_cost, 4),
        "estimated_duration_minutes": round(estimated_duration, 1),
        "blocked_tasks": blocked_tasks,
    }
