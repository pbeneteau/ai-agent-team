# Backend config boundaries

- `settings.py`: environment and deployment inputs only.
- `token_budgets.py`, `prompts.py`, `knowledge.py`, `team_recommendations.py`, `tool_runtime.py`, `pricing.py`, `brief.py`, `document_limits.py`: runtime policy and product tuning.
- Persistent product state stays outside this package (`data/`, project brief state, workspaces, task deliverables, caches).

Keep secrets and local environment overrides in `.env`, not in runtime policy modules.
