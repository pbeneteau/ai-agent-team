"""Workspace isolation dependency.

MVP: returns hardcoded workspace_id = "1".
Post-MVP: extract workspace from JWT / session.
"""


async def get_workspace_id() -> str:
    """FastAPI dependency that returns the current workspace ID.

    Usage in route handlers::

        @router.get("/api/things")
        async def list_things(workspace_id: str = Depends(get_workspace_id)):
            ...
    """
    return "1"
