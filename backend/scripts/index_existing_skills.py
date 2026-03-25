"""
One-time migration script: index all existing core_skills and research files into ChromaDB
for ARCH-1 vector retrieval.

Usage:
    cd backend && python -m scripts.index_existing_skills
"""
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.core.workspace import get_workspace_manager
from app.memory.vector_store import get_vector_store


def main():
    settings = get_settings()
    wm = get_workspace_manager()
    vs = get_vector_store()
    base = Path(settings.workspaces_dir)

    if not base.exists():
        print(f"Workspaces directory not found: {base}")
        return

    total_chunks = 0
    for ws_dir in sorted(base.iterdir()):
        if not ws_dir.is_dir():
            continue
        agent_id = ws_dir.name
        skills_dir = ws_dir / "skills"
        if not skills_dir.exists():
            continue

        collection_name = f"agent_skills_{agent_id}"
        indexed = 0

        # Index core_skills
        core_skills_path = skills_dir / "core_skills.md"
        if core_skills_path.exists():
            content = core_skills_path.read_text(encoding="utf-8")
            count = vs.upsert_chunked(
                collection_name, content, base_id="core_skills",
                metadata={"skill_name": "core_skills", "agent_id": agent_id},
            )
            indexed += count

        # Index research files
        for research_file in sorted(skills_dir.glob("research_*.md")):
            content = research_file.read_text(encoding="utf-8")
            count = vs.upsert_chunked(
                collection_name, content, base_id=research_file.stem,
                metadata={"skill_name": research_file.stem, "agent_id": agent_id},
            )
            indexed += count

        if indexed:
            print(f"  {agent_id}: {indexed} chunks indexed")
            total_chunks += indexed

    print(f"\nDone. Total: {total_chunks} chunks indexed across all agents.")


if __name__ == "__main__":
    main()
