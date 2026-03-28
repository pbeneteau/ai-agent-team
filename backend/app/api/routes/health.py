"""Health check endpoint.

Ref: TDD-04 Section 13.

Checks PostgreSQL connection, Redis ping, MinIO bucket exists.
Returns 200 with per-service status if all healthy, 503 if any service is down.
Checks run concurrently via asyncio.gather.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """Concurrent health checks for all infrastructure services."""
    db_status, redis_status, s3_status = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_s3(),
    )

    services = {
        "database": db_status,
        "redis": redis_status,
        "s3": s3_status,
    }

    all_healthy = all(v == "ok" for v in services.values())
    status_code = 200 if all_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "version": "2.0.0",
            "services": services,
        },
    )


async def _check_database() -> str:
    """Check PostgreSQL connectivity by executing a simple query."""
    try:
        from app.core.database import async_session_maker
        from sqlalchemy import text

        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("Health check: database failed — %s", exc)
        return "error"


async def _check_redis() -> str:
    """Check Redis connectivity via PING."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            result = await client.ping()
            return "ok" if result else "error"
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning("Health check: redis failed — %s", exc)
        return "error"


async def _check_s3() -> str:
    """Check MinIO/S3 connectivity by verifying the bucket exists."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        # Run the synchronous boto3 call in a thread to avoid blocking
        def _check() -> str:
            client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name="us-east-1",
            )
            try:
                client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
                return "ok"
            except ClientError:
                return "error"

        return await asyncio.to_thread(_check)
    except Exception as exc:
        logger.warning("Health check: s3 failed — %s", exc)
        return "error"
