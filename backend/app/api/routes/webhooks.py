"""GitHub and GitLab webhook receivers.

Ref: TDD-04 Section 10, TDD-02 Section 7.2-7.3.

Security:
- GitHub: verify X-Hub-Signature-256 using stored webhook_secret (HMAC-SHA256)
- GitLab: verify X-Gitlab-Token header against stored webhook_secret
- Always return 200 (even on internal errors — log instead)
- Deduplicate via external_comment_id unique constraint
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.celery_app import execute_artifact_dag
from app.core.database import async_session_maker
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.contextual_comment import ContextualComment
from app.models.enums import ArtifactStatus, CommentSource, WaveTrigger
from app.models.execution_wave import ExecutionWave
from app.models.git_provider_connection import GitProviderConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# POST /api/webhooks/github
# ---------------------------------------------------------------------------


@router.post("/github")
async def github_webhook(request: Request) -> JSONResponse:
    """Receive and process GitHub webhook events."""
    try:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Verify signature
        if not await _verify_github_signature(body, signature):
            return JSONResponse({"status": "invalid_signature"}, status_code=401)

        payload = await request.json()
        event_type = request.headers.get("X-GitHub-Event", "")

        logger.info("GitHub webhook received: event=%s", event_type)

        await _handle_github_event(event_type, payload)

    except Exception:
        logger.exception("Error processing GitHub webhook (returning 200)")

    return JSONResponse({"status": "ok"}, status_code=200)


# ---------------------------------------------------------------------------
# POST /api/webhooks/gitlab
# ---------------------------------------------------------------------------


@router.post("/gitlab")
async def gitlab_webhook(request: Request) -> JSONResponse:
    """Receive and process GitLab webhook events."""
    try:
        gitlab_token = request.headers.get("X-Gitlab-Token", "")

        # Verify token
        if not await _verify_gitlab_token(gitlab_token):
            return JSONResponse({"status": "invalid_token"}, status_code=401)

        payload = await request.json()
        event_type = payload.get("object_kind", "")

        logger.info("GitLab webhook received: event=%s", event_type)

        await _handle_gitlab_event(event_type, payload)

    except Exception:
        logger.exception("Error processing GitLab webhook (returning 200)")

    return JSONResponse({"status": "ok"}, status_code=200)


# ---------------------------------------------------------------------------
# Signature / token verification
# ---------------------------------------------------------------------------


async def _verify_github_signature(body: bytes, signature: str) -> bool:
    """Verify GitHub X-Hub-Signature-256 against all stored webhook secrets.

    Uses timing-safe comparison (hmac.compare_digest).
    """
    if not signature.startswith("sha256="):
        return False

    received_sig = signature[7:]  # strip "sha256=" prefix

    async with async_session_maker() as db:
        result = await db.execute(
            select(GitProviderConnection.webhook_secret).where(
                GitProviderConnection.provider == "github",
                GitProviderConnection.webhook_secret.is_not(None),
            )
        )
        secrets = result.scalars().all()

    for secret in secrets:
        expected = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected, received_sig):
            return True

    return False


async def _verify_gitlab_token(token: str) -> bool:
    """Verify GitLab X-Gitlab-Token against stored webhook secrets."""
    if not token:
        return False

    async with async_session_maker() as db:
        result = await db.execute(
            select(GitProviderConnection.webhook_secret).where(
                GitProviderConnection.provider == "gitlab",
                GitProviderConnection.webhook_secret.is_not(None),
            )
        )
        secrets = result.scalars().all()

    return any(hmac.compare_digest(secret, token) for secret in secrets)


# ---------------------------------------------------------------------------
# GitHub event handlers
# ---------------------------------------------------------------------------


async def _handle_github_event(event_type: str, payload: dict) -> None:
    """Dispatch GitHub events to the appropriate handler."""
    if event_type == "pull_request_review_comment":
        await _handle_pr_review_comment(payload, source=CommentSource.GITHUB_PR)

    elif event_type == "pull_request_review":
        await _handle_pr_review(payload, source=CommentSource.GITHUB_PR)

    elif event_type == "pull_request":
        action = payload.get("action", "")
        merged = payload.get("pull_request", {}).get("merged", False)

        if action == "closed" and merged:
            await _handle_pr_merged(payload)
        elif action == "closed" and not merged:
            logger.info("PR closed without merging — no action")
        else:
            logger.debug("Ignoring pull_request action=%s", action)
    else:
        logger.debug("Ignoring GitHub event: %s", event_type)


# ---------------------------------------------------------------------------
# GitLab event handlers
# ---------------------------------------------------------------------------


async def _handle_gitlab_event(event_type: str, payload: dict) -> None:
    """Dispatch GitLab events to the appropriate handler."""
    if event_type == "note":
        # Note on a merge request
        noteable_type = payload.get("object_attributes", {}).get("noteable_type", "")
        if noteable_type == "MergeRequest":
            await _handle_gitlab_mr_note(payload)

    elif event_type == "merge_request":
        action = payload.get("object_attributes", {}).get("action", "")
        state = payload.get("object_attributes", {}).get("state", "")

        if action == "merge" or state == "merged":
            await _handle_gitlab_mr_merged(payload)
        elif action == "close":
            logger.info("MR closed without merging — no action")
        else:
            logger.debug("Ignoring merge_request action=%s", action)
    else:
        logger.debug("Ignoring GitLab event: %s", event_type)


# ---------------------------------------------------------------------------
# Shared event processing
# ---------------------------------------------------------------------------


async def _handle_pr_review_comment(payload: dict, source: CommentSource) -> None:
    """Handle inline PR/MR comment → create contextual_comment + trigger iteration."""
    pr_number = payload.get("pull_request", {}).get("number")
    comment = payload.get("comment", {})
    comment_id = str(comment.get("id", ""))
    comment_body = comment.get("body", "")
    file_path = comment.get("path")
    position = comment.get("position")

    if not pr_number or not comment_body:
        return

    await _create_comment_and_iterate(
        pr_number=pr_number,
        external_comment_id=comment_id,
        instruction=comment_body,
        file_path=file_path,
        highlight_start=position,
        source=source,
    )


async def _handle_pr_review(payload: dict, source: CommentSource) -> None:
    """Handle PR review with changes_requested → create comment + trigger iteration."""
    review = payload.get("review", {})
    state = review.get("state", "")
    body = review.get("body", "")
    review_id = str(review.get("id", ""))
    pr_number = payload.get("pull_request", {}).get("number")

    if state != "changes_requested" or not body or not pr_number:
        return

    await _create_comment_and_iterate(
        pr_number=pr_number,
        external_comment_id=review_id,
        instruction=body,
        file_path=None,
        highlight_start=None,
        source=source,
    )


async def _handle_pr_merged(payload: dict) -> None:
    """Handle PR merged → approve artifact."""
    pr_number = payload.get("pull_request", {}).get("number")
    if not pr_number:
        return

    async with async_session_maker() as db:
        artifact = await _find_artifact_by_pr(db, pr_number)
        if artifact is None:
            logger.info("No artifact found for PR #%s — ignoring", pr_number)
            return

        artifact.status = ArtifactStatus.APPROVED.value
        artifact.approved_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "Artifact %s approved via PR merge (PR #%s)",
            artifact.id, pr_number,
        )


async def _handle_gitlab_mr_note(payload: dict) -> None:
    """Handle GitLab note on MR → create comment + trigger iteration."""
    mr = payload.get("merge_request", {})
    mr_iid = mr.get("iid")
    note = payload.get("object_attributes", {})
    note_id = str(note.get("id", ""))
    note_body = note.get("note", "")

    if not mr_iid or not note_body:
        return

    # GitLab notes on MRs don't have file_path in the same format as GitHub
    # For diff notes, position info is in the note
    position = note.get("position", {})
    file_path = position.get("new_path") or position.get("old_path")

    await _create_comment_and_iterate(
        pr_number=mr_iid,
        external_comment_id=note_id,
        instruction=note_body,
        file_path=file_path,
        highlight_start=position.get("new_line") if position else None,
        source=CommentSource.GITLAB_MR,
    )


async def _handle_gitlab_mr_merged(payload: dict) -> None:
    """Handle GitLab MR merged → approve artifact."""
    mr = payload.get("object_attributes", {})
    mr_iid = mr.get("iid")
    if not mr_iid:
        return

    async with async_session_maker() as db:
        artifact = await _find_artifact_by_pr(db, mr_iid)
        if artifact is None:
            logger.info("No artifact found for MR !%s — ignoring", mr_iid)
            return

        artifact.status = ArtifactStatus.APPROVED.value
        artifact.approved_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "Artifact %s approved via MR merge (MR !%s)",
            artifact.id, mr_iid,
        )


# ---------------------------------------------------------------------------
# Core: create comment + trigger iteration
# ---------------------------------------------------------------------------


async def _create_comment_and_iterate(
    pr_number: int,
    external_comment_id: str,
    instruction: str,
    file_path: str | None,
    highlight_start: int | None,
    source: CommentSource,
) -> None:
    """Create a contextual comment and trigger an iteration execution wave."""
    async with async_session_maker() as db:
        # Find artifact by PR number
        artifact = await _find_artifact_by_pr(db, pr_number)
        if artifact is None:
            logger.info("No artifact found for PR/MR #%s — ignoring", pr_number)
            return

        # Find latest version to attach comment to
        result = await db.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact.id)
            .order_by(ArtifactVersion.version_number.desc())
            .limit(1)
        )
        latest_version = result.scalar_one_or_none()
        if latest_version is None:
            logger.warning(
                "No versions found for artifact %s — cannot attach comment",
                artifact.id,
            )
            return

        # Create contextual comment (dedup via external_comment_id unique constraint)
        comment = ContextualComment(
            artifact_version_id=latest_version.id,
            file_path=file_path,
            highlight_start=highlight_start,
            instruction=instruction,
            source=source.value,
            external_comment_id=external_comment_id,
        )
        db.add(comment)

        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            logger.info(
                "Duplicate external comment %s — skipping", external_comment_id
            )
            return

        # Import router to get a DAG plan for iteration
        from app.agents.router import route_brief

        # Build a simple iteration routing
        brief_data = {
            "title": artifact.title,
            "goal": artifact.goal,
            "description": artifact.description,
            "artifact_type": artifact.artifact_type,
            "iteration_instruction": instruction,
        }

        try:
            routing = await route_brief(
                brief_data=brief_data,
                workspace_id=artifact.project_id,  # Will be resolved in route_brief
                db=db,
            )
        except Exception:
            logger.exception("Failed to route iteration for artifact %s", artifact.id)
            await db.commit()
            return

        # Create execution wave
        wave = ExecutionWave(
            artifact_id=artifact.id,
            trigger=WaveTrigger.ITERATION.value,
            trigger_comment_id=comment.id,
            dag_plan=routing.dag_plan,
            assembled_team=routing.assembled_team,
            total_steps=len(routing.dag_plan.get("waves", [])),
            step_labels=routing.step_labels,
        )
        db.add(wave)

        # Set artifact back to drafting
        artifact.status = ArtifactStatus.DRAFTING.value

        await db.commit()

        # Enqueue Celery task
        execute_artifact_dag.delay(wave.id)

        logger.info(
            "Iteration triggered for artifact %s via %s comment %s",
            artifact.id, source.value, external_comment_id,
        )


async def _find_artifact_by_pr(
    db, pr_number: int
) -> Artifact | None:
    """Find an artifact by its git_pr_number."""
    result = await db.execute(
        select(Artifact).where(Artifact.git_pr_number == pr_number).limit(1)
    )
    return result.scalar_one_or_none()
