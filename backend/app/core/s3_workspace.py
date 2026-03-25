"""S3-backed workspace manager for stateless artifact storage.

Artifacts are stored in MinIO (S3-compatible) under:
    s3://{bucket}/artifacts/{artifact_id}/v{version}/artifact

Methods
-------
upload_artifact_version(content, artifact_id, version)
    Upload text content for a specific artifact version.
download_artifact_version(s3_path)
    Download text content from an S3 path.
get_artifact_diff(old_s3_path, new_s3_path)
    Return a unified diff string between two stored versions.
"""

import difflib
import logging

import aioboto3

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class S3WorkspaceManager:
    """Manages artifact files in S3-compatible object storage (MinIO)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._endpoint_url = settings.s3_endpoint_url
        self._access_key = settings.s3_access_key
        self._secret_key = settings.s3_secret_key
        self._bucket = settings.s3_bucket_name
        self._region = settings.s3_region
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict:
        return {
            "service_name": "s3",
            "endpoint_url": self._endpoint_url,
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "region_name": self._region,
        }

    async def _ensure_bucket(self, client) -> None:
        """Create the bucket if it does not exist."""
        try:
            await client.head_bucket(Bucket=self._bucket)
        except client.exceptions.ClientError:
            await client.create_bucket(Bucket=self._bucket)
            logger.info("Created S3 bucket: %s", self._bucket)

    @staticmethod
    def _s3_key(artifact_id: str, version: int) -> str:
        return f"artifacts/{artifact_id}/v{version}/artifact"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def upload_artifact_version(
        self, content: str, artifact_id: str, version: int
    ) -> str:
        """Upload text content and return the S3 key."""
        key = self._s3_key(artifact_id, version)
        async with self._session.client(**self._client_kwargs()) as client:
            await self._ensure_bucket(client)
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
        logger.info("Uploaded artifact %s v%d -> s3://%s/%s", artifact_id, version, self._bucket, key)
        return key

    async def download_artifact_version(self, s3_path: str) -> str:
        """Download and return the text content at the given S3 key."""
        async with self._session.client(**self._client_kwargs()) as client:
            response = await client.get_object(Bucket=self._bucket, Key=s3_path)
            body = await response["Body"].read()
        return body.decode("utf-8")

    async def get_artifact_diff(self, old_s3_path: str, new_s3_path: str) -> str:
        """Return a unified diff between two artifact versions stored in S3."""
        old_content = await self.download_artifact_version(old_s3_path)
        new_content = await self.download_artifact_version(new_s3_path)

        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_s3_path,
            tofile=new_s3_path,
        )
        return "".join(diff)
