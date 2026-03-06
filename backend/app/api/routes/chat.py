import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse

from app.api.websocket_manager import get_manager
from app.agents.associate import get_associate_chat
from app.core.team_builder import get_team_builder_session, reset_team_builder_session
from app.core.orchestrator import get_orchestrator
from app.core.learning import run_learning_phase_for_team
from app.models.chat import ChatMessageIn
from app.core.agent_factory import get_agent_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "credit balance is too low" in msg or "insufficient_quota" in msg:
        return "Solde Anthropic insuffisant. Rechargez votre compte sur console.anthropic.com → Plans & Billing."
    if "invalid_api_key" in msg or "authentication" in msg.lower():
        return "Clé API Anthropic invalide. Vérifiez ANTHROPIC_API_KEY dans votre fichier .env."
    if "rate_limit" in msg or "429" in msg:
        return "Limite de requêtes Anthropic atteinte. Réessayez dans quelques secondes."
    if "overloaded" in msg or "529" in msg:
        return "Les serveurs Anthropic sont surchargés. Réessayez dans un moment."
    if "connection" in msg.lower() or "timeout" in msg.lower():
        return "Impossible de joindre l'API Anthropic. Vérifiez votre connexion internet."
    return f"Erreur inattendue : {msg[:200]}"


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    manager = get_manager()
    await manager.connect(websocket)
    logger.info(f"Chat WS opened from {websocket.client}")
    associate = get_associate_chat()
    orchestrator = get_orchestrator()

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            message_type = data.get("type", "chat")
            content = data.get("content", "")

            if message_type in ("chat", "form_response"):
                # form_response: convert structured form values to a readable chat message
                if message_type == "form_response":
                    values: dict = data.get("values", {})
                    form_title: str = data.get("form_title", "")
                    lines = [f"Voici mes informations pour « {form_title} » :" if form_title else "Voici mes informations :"]
                    for k, v in values.items():
                        lines.append(f"- {k} : {v}")
                    content = "\n".join(lines)

                full_response = ""
                tagged_doc_ids: list[str] = data.get("tagged_doc_ids", [])
                await manager.send_personal({"type": "stream_start"}, websocket)

                async for chunk in associate.chat(content, tagged_doc_ids=tagged_doc_ids):
                    full_response += chunk
                    await manager.send_personal({"type": "stream_chunk", "data": chunk}, websocket)

                # Check if associate requested an action
                action = associate.extract_action(full_response)
                if action:
                    action_type = action.get("action")

                    if action_type == "start_team_builder":
                        await manager.send_personal({"type": "navigate", "data": {"to": "team-builder"}}, websocket)

                    elif action_type == "create_team_direct":
                        from app.core.learning import run_learning_phase_for_team
                        from app.agents.specialists.templates import TEAM_TEMPLATES
                        from app.memory.project_context import get_project_context_store
                        project = action.get("project", {})
                        teams_spec = action.get("teams", [])
                        ctx_store = get_project_context_store()
                        ctx_store.save_context({
                            "name": project.get("name", "Unnamed Project"),
                            "description": project.get("description", ""),
                            "domain": project.get("domain", ""),
                        })

                        created_teams = []
                        created_agents = []
                        new_team_ids: list[str] = []
                        for team_spec in teams_spec:
                            template_key = team_spec.get("template")
                            if template_key and template_key in TEAM_TEMPLATES:
                                # Template-based team
                                team, agents = get_agent_factory().create_team_from_template(template_key)
                            elif "agents" in team_spec:
                                # Custom team with full agent specs
                                team, agents = get_agent_factory().create_custom_team(
                                    name=team_spec.get("name", project.get("name", "Team")),
                                    description=team_spec.get("description", ""),
                                    domain=team_spec.get("domain", project.get("domain", "")),
                                    agent_specs=team_spec["agents"],
                                )
                            else:
                                continue
                            created_teams.append(team.model_dump())
                            created_agents.extend([a.model_dump() for a in agents])
                            new_team_ids.append(team.id)

                        await manager.send_personal({
                            "type": "team_created",
                            "data": {"project": project, "teams": created_teams, "agents": created_agents},
                        }, websocket)
                        # Launch learning phase only for newly created teams
                        for team_id in new_team_ids:
                            asyncio.create_task(
                                run_learning_phase_for_team(team_id, broadcast_callback=manager.broadcast)
                            )

                    elif action_type == "create_task":
                        from app.models.task import TaskPriority
                        task = orchestrator.create_task(
                            title=action.get("title", "Task"),
                            description=action.get("description", ""),
                            priority=TaskPriority(action.get("priority", "medium")),
                            team_id=action.get("team_id"),
                        )
                        await manager.send_personal({"type": "task_created", "data": task.model_dump()}, websocket)
                        # Launch task execution asynchronously
                        asyncio.create_task(
                            orchestrator.execute_task(task.id, broadcast=manager.broadcast)
                        )

                await manager.send_personal({"type": "stream_end", "data": full_response}, websocket)

            elif message_type == "ping":
                await manager.send_personal({"type": "pong"}, websocket)

    except WebSocketDisconnect:
        logger.info(f"Chat WS closed by client: {websocket.client}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"Chat WS error: {e}")
        error_message = _friendly_error(e)
        try:
            await manager.send_personal({"type": "error", "data": error_message}, websocket)
        except Exception:
            pass
        manager.disconnect(websocket)


@router.websocket("/team-builder/ws")
async def team_builder_websocket(websocket: WebSocket):
    manager = get_manager()
    await manager.connect(websocket)
    logger.info(f"Team-builder WS opened from {websocket.client}")
    session = get_team_builder_session()

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            message_type = data.get("type", "chat")
            content = data.get("content", "")

            if message_type in ("chat", "form_response"):
                # form_response: convert structured form values to a readable chat message
                if message_type == "form_response":
                    values: dict = data.get("values", {})
                    form_title: str = data.get("form_title", "")
                    lines = [f"Voici mes informations pour « {form_title} » :" if form_title else "Voici mes informations :"]
                    for k, v in values.items():
                        lines.append(f"- {k} : {v}")
                    content = "\n".join(lines)

                full_response = ""
                await manager.send_personal({"type": "stream_start"}, websocket)

                async for chunk in session.chat(content):
                    full_response += chunk
                    await manager.send_personal({"type": "stream_chunk", "data": chunk}, websocket)

                await manager.send_personal({"type": "stream_end", "data": full_response}, websocket)

                if session.is_confirmed():
                    await manager.send_personal({"type": "team_confirmed"}, websocket)

            elif message_type == "confirm_team":
                result = await session.create_team_from_proposal()
                await manager.send_personal({"type": "team_created", "data": result}, websocket)

                # Launch learning phase only for newly created teams
                for team_dict in result.get("teams", []):
                    team_id = team_dict.get("id")
                    if team_id:
                        asyncio.create_task(
                            run_learning_phase_for_team(team_id, broadcast_callback=manager.broadcast)
                        )
                reset_team_builder_session()

            elif message_type == "ping":
                await manager.send_personal({"type": "pong"}, websocket)

    except WebSocketDisconnect:
        logger.info(f"Team-builder WS closed by client: {websocket.client}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"Team-builder WS error: {e}")
        manager.disconnect(websocket)
