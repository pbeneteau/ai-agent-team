import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.agents.associate import AssociateChat
from app.api.websocket_manager import get_manager
from app.core.agent_factory import get_agent_factory
from app.core.learning import run_learning_phase
from app.core.orchestrator import get_orchestrator
from app.core.team_builder import get_team_builder_session, reset_team_builder_session
from app.core.universal_plan import (
    PlanClarificationRequiredError,
    TaskPlanExecutor,
    TeamPlanExecutor,
    UniversalPlanSession,
)
from app.models.agent import AgentConfig, AgentRole
from app.models.chat_actions import (
    AssistantAction,
    GatherInfoAction,
    StartTeamBuilderAction,
    TaskPlanProposalAction,
    TeamPlanProposalAction,
    TriggerLearningAction,
)
from app.models.plan import PlanKind, PlanState

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
    if "learning targets" in msg.lower():
        return "Alex n'a trouvé aucun agent ou équipe valide à relancer. Réessayez en ciblant des agents existants."
    return f"Erreur inattendue : {msg[:200]}"


def _resolve_learning_targets(action: TriggerLearningAction) -> list[AgentConfig]:
    factory = get_agent_factory()
    selected: dict[str, AgentConfig] = {}

    all_agents = [
        agent for agent in factory.list_agents()
        if agent.role != AgentRole.ASSOCIATE
    ]
    all_teams = factory.list_teams()

    agents_by_id = {agent.id: agent for agent in all_agents}
    teams_by_id = {team.id: team for team in all_teams}
    agents_by_name = {agent.name.strip().lower(): agent for agent in all_agents}
    teams_by_name = {team.name.strip().lower(): team for team in all_teams}

    for agent_id in action.agent_ids:
        agent = agents_by_id.get(agent_id)
        if agent:
            selected[agent.id] = agent

    for team_id in action.team_ids:
        team = teams_by_id.get(team_id)
        if not team:
            continue
        for agent in factory.get_team_agents(team.id):
            if agent.role != AgentRole.ASSOCIATE:
                selected[agent.id] = agent

    for agent_name in action.agent_names:
        agent = agents_by_name.get(agent_name.strip().lower())
        if agent:
            selected[agent.id] = agent

    for team_name in action.team_names:
        team = teams_by_name.get(team_name.strip().lower())
        if not team:
            continue
        for agent in factory.get_team_agents(team.id):
            if agent.role != AgentRole.ASSOCIATE:
                selected[agent.id] = agent

    if not selected:
        raise ValueError("No valid learning targets found")

    return list(selected.values())


def _form_response_to_text(values: dict, form_title: str = "") -> str:
    lines = [f"Voici mes informations pour « {form_title} » :" if form_title else "Voici mes informations :"]
    for key, value in values.items():
        lines.append(f"- {key} : {value}")
    return "\n".join(lines)


async def _stream_associate_response(
    *,
    associate: AssociateChat,
    manager,
    websocket: WebSocket,
    content: str,
    tagged_doc_ids: list[str],
):
    await manager.send_personal({"type": "stream_start"}, websocket)
    response = await associate.stream_response(
        content,
        tagged_doc_ids=tagged_doc_ids,
        on_text_chunk=lambda chunk: manager.send_personal({"type": "stream_chunk", "data": chunk}, websocket),
    )
    return response


async def _emit_plan_preview(*, manager, websocket: WebSocket, plan_session: UniversalPlanSession):
    if not plan_session.draft:
        return
    await manager.send_personal(
        {
            "type": "plan_preview",
            "data": {
                "session_id": plan_session.session_id,
                "state": plan_session.state.value,
                "kind": plan_session.kind.value if plan_session.kind else None,
                "last_error": plan_session.last_error,
                "draft": plan_session.draft.model_dump(mode="json"),
            },
        },
        websocket,
    )
    await manager.send_personal(
        {
            "type": "plan_confirmation_required",
            "data": {
                "session_id": plan_session.session_id,
                "kind": plan_session.kind.value if plan_session.kind else None,
            },
        },
        websocket,
    )


def _clarification_values_to_text(values: dict[str, str]) -> str:
    lines = ["Clarifications structurées de l'utilisateur:"]
    for key, value in values.items():
        text = str(value or "").strip()
        if not text:
            continue
        lines.append(f"- {key}: {text}")
    return "\n".join(lines)


async def _emit_plan_failed(*, manager, websocket: WebSocket, plan_session: UniversalPlanSession, error: str):
    await manager.send_personal(
        {
            "type": "plan_failed",
            "data": {
                "session_id": plan_session.session_id,
                "state": plan_session.state.value,
                "kind": plan_session.kind.value if plan_session.kind else None,
                "draft": plan_session.draft.model_dump(mode="json") if plan_session.draft else None,
                "error": error,
            },
        },
        websocket,
    )


def _require_plan_identity(data: dict) -> tuple[str, str]:
    session_id = str(data.get("session_id") or "").strip()
    draft_id = str(data.get("draft_id") or "").strip()
    if not session_id:
        raise ValueError("Missing plan session_id")
    if not draft_id:
        raise ValueError("Missing plan draft_id")
    return session_id, draft_id


async def _handle_associate_action(
    *,
    action: AssistantAction,
    manager,
    websocket: WebSocket,
    plan_session: UniversalPlanSession,
    tagged_doc_ids: list[str],
):
    if isinstance(action, StartTeamBuilderAction):
        await manager.send_personal({"type": "navigate", "data": {"to": "team-builder"}}, websocket)
        return

    if isinstance(action, GatherInfoAction):
        plan_session.set_form_from_action(action)
        await manager.send_personal(
            {
                "type": "plan_form",
                "data": {
                    "session_id": plan_session.session_id,
                    "form": plan_session.form.model_dump(mode="json") if plan_session.form else None,
                },
            },
            websocket,
        )
        return

    if isinstance(action, TaskPlanProposalAction):
        plan_session.set_task_draft(action, tagged_doc_ids)
        await _emit_plan_preview(manager=manager, websocket=websocket, plan_session=plan_session)
        return

    if isinstance(action, TeamPlanProposalAction):
        plan_session.set_team_draft(action)
        await _emit_plan_preview(manager=manager, websocket=websocket, plan_session=plan_session)
        return

    if isinstance(action, TriggerLearningAction):
        target_agents = _resolve_learning_targets(action)
        logger.info(
            "Triggering learning phase for %s agent(s): %s",
            len(target_agents),
            [agent.id for agent in target_agents],
        )
        for agent in target_agents:
            asyncio.create_task(
                run_learning_phase(agent, broadcast_callback=manager.broadcast)
            )
        return

    raise ValueError(f"Unsupported associate action type: {type(action).__name__}")


async def _execute_confirmed_plan(
    *,
    manager,
    websocket: WebSocket,
    plan_session: UniversalPlanSession,
    session_id: str,
    draft_id: str,
):
    try:
        should_execute, completed_payload = plan_session.can_confirm(
            session_id=session_id,
            draft_id=draft_id,
        )
    except PlanClarificationRequiredError as exc:
        plan_session.mark_clarification_required(exc.draft, str(exc))
        await _emit_plan_preview(manager=manager, websocket=websocket, plan_session=plan_session)
        return
    if not should_execute and completed_payload is not None:
        await manager.send_personal(
            {
                "type": "plan_completed",
                "data": {
                    "session_id": plan_session.session_id,
                    "kind": plan_session.kind.value if plan_session.kind else None,
                    "result": completed_payload,
                },
            },
            websocket,
        )
        return

    try:
        plan_session.validate_before_execute()
    except PlanClarificationRequiredError as exc:
        plan_session.mark_clarification_required(exc.draft, str(exc))
        await _emit_plan_preview(manager=manager, websocket=websocket, plan_session=plan_session)
        return
    if not plan_session.draft or not plan_session.kind:
        raise ValueError("No plan draft available")

    plan_session.mark_executing(draft_id)
    await manager.send_personal(
        {
            "type": "plan_executing",
            "data": {
                "session_id": plan_session.session_id,
                "draft_id": draft_id,
                "kind": plan_session.kind.value,
                "draft": plan_session.draft.model_dump(mode="json"),
            },
        },
        websocket,
    )

    try:
        if plan_session.kind == PlanKind.TASK:
            result = await TaskPlanExecutor().execute(plan_session.draft, manager.broadcast)
            payload = result.model_dump()
        elif plan_session.kind == PlanKind.TEAM:
            payload = await TeamPlanExecutor().execute(plan_session.draft, manager.broadcast)
        else:
            raise ValueError(f"Unsupported plan kind: {plan_session.kind}")
    except PlanClarificationRequiredError as exc:
        plan_session.mark_clarification_required(exc.draft, str(exc))
        await _emit_plan_preview(manager=manager, websocket=websocket, plan_session=plan_session)
        return
    except Exception as exc:
        plan_session.mark_failed(str(exc))
        raise

    plan_session.mark_completed(draft_id, payload)
    await manager.send_personal(
        {
            "type": "plan_completed",
            "data": {
                "session_id": plan_session.session_id,
                "draft_id": draft_id,
                "kind": plan_session.kind.value,
                "result": payload,
            },
        },
        websocket,
    )


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    manager = get_manager()
    await manager.connect(websocket)
    logger.info(f"Chat WS opened from {websocket.client}")
    associate = AssociateChat()
    plan_session = UniversalPlanSession(session_id=uuid4().hex)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            message_type = data.get("type", "chat")
            content = data.get("content", "")

            try:
                if message_type in ("chat", "form_response"):
                    if message_type == "form_response":
                        content = _form_response_to_text(
                            data.get("values", {}),
                            data.get("form_title", ""),
                        )
                        plan_session.form = None

                    tagged_doc_ids: list[str] = data.get("tagged_doc_ids", [])
                    response = await _stream_associate_response(
                        associate=associate,
                        manager=manager,
                        websocket=websocket,
                        content=content,
                        tagged_doc_ids=tagged_doc_ids,
                    )
                    await manager.send_personal({"type": "stream_end", "data": response.human_text}, websocket)
                    if response.action:
                        await _handle_associate_action(
                            action=response.action,
                            manager=manager,
                            websocket=websocket,
                            plan_session=plan_session,
                            tagged_doc_ids=tagged_doc_ids,
                        )

                elif message_type == "plan_confirm":
                    session_id, draft_id = _require_plan_identity(data)
                    await _execute_confirmed_plan(
                        manager=manager,
                        websocket=websocket,
                        plan_session=plan_session,
                        session_id=session_id,
                        draft_id=draft_id,
                    )

                elif message_type == "plan_cancel":
                    session_id, draft_id = _require_plan_identity(data)
                    if session_id != plan_session.session_id:
                        raise ValueError("Plan session obsolete")
                    if plan_session.state == PlanState.EXECUTING:
                        raise ValueError("Plan execution already in progress")
                    if not plan_session.draft or plan_session.draft.id != draft_id:
                        raise ValueError("Plan draft obsolete")
                    plan_session.cancel()
                    await manager.send_personal(
                        {
                            "type": "plan_cancelled",
                            "data": {
                                "session_id": session_id,
                                "draft_id": draft_id,
                                "state": plan_session.state.value,
                            },
                        },
                        websocket,
                    )

                elif message_type == "plan_revise":
                    session_id, draft_id = _require_plan_identity(data)
                    if session_id != plan_session.session_id:
                        raise ValueError("Plan session obsolete")
                    if not plan_session.draft or plan_session.draft.id != draft_id:
                        raise ValueError("Plan draft obsolete")
                    if plan_session.state not in {PlanState.AWAITING_CONFIRMATION, PlanState.FAILED}:
                        raise ValueError("Plan cannot be revised in its current state")
                    revision = data.get("content", "").strip()
                    clarification_values = {
                        str(key): str(value)
                        for key, value in (data.get("clarification_values") or {}).items()
                    }
                    if clarification_values:
                        plan_session.apply_clarification_values(clarification_values)
                    if not revision and clarification_values:
                        await _emit_plan_preview(
                            manager=manager,
                            websocket=websocket,
                            plan_session=plan_session,
                        )
                        continue
                    plan_session.mark_revising()
                    await manager.send_personal(
                        {
                            "type": "plan_revising",
                            "data": {
                                "session_id": session_id,
                                "draft_id": draft_id,
                                "state": plan_session.state.value,
                            },
                        },
                        websocket,
                    )
                    revision_prompt_parts = ["Merci, voici ce que je veux modifier dans le plan proposé:"]
                    if clarification_values:
                        revision_prompt_parts.append(_clarification_values_to_text(clarification_values))
                    revision_prompt_parts.append(revision or "Je veux une version révisée.")
                    revision_prompt = "\n".join(revision_prompt_parts)
                    response = await _stream_associate_response(
                        associate=associate,
                        manager=manager,
                        websocket=websocket,
                        content=revision_prompt,
                        tagged_doc_ids=[],
                    )
                    await manager.send_personal({"type": "stream_end", "data": response.human_text}, websocket)
                    if response.action:
                        await _handle_associate_action(
                            action=response.action,
                            manager=manager,
                            websocket=websocket,
                            plan_session=plan_session,
                            tagged_doc_ids=[],
                        )

                elif message_type == "ping":
                    await manager.send_personal({"type": "pong"}, websocket)
            except Exception as e:
                logger.exception("Chat WS message error: %s", e)
                if message_type.startswith("plan_"):
                    if plan_session.state == PlanState.EXECUTING:
                        plan_session.mark_failed(str(e))
                    await _emit_plan_failed(
                        manager=manager,
                        websocket=websocket,
                        plan_session=plan_session,
                        error=_friendly_error(e),
                    )
                await manager.send_personal({"type": "error", "data": _friendly_error(e)}, websocket)

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
    logger.warning("Deprecated team-builder websocket in use; prefer /chat/ws with team-builder mode.")
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
                reset_team_builder_session()

            elif message_type == "ping":
                await manager.send_personal({"type": "pong"}, websocket)

    except WebSocketDisconnect:
        logger.info(f"Team-builder WS closed by client: {websocket.client}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"Team-builder WS error: {e}")
        manager.disconnect(websocket)
