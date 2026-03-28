"""
S3 workspace module — single interface between the application and object storage.

Path conventions (TDD-02 Section 4):
  Artifact files:  artifacts/{artifact_id}/v{version}/{relative_path}
  Documents:       documents/{document_id}/{filename}

All operations target the single bucket configured in settings.S3_BUCKET_NAME.
"""

import logging
import mimetypes
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: "S3Client | None" = None


def _get_client() -> "S3Client":
    """Return a cached boto3 S3 client configured for MinIO/S3."""
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="us-east-1",
        )
    return _client


def _guess_content_type(filename: str) -> str:
    """Guess MIME type from filename extension, defaulting to binary."""
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or "application/octet-stream"


# ---------------------------------------------------------------------------
# Bucket management
# ---------------------------------------------------------------------------


def ensure_bucket() -> None:
    """Create the configured bucket if it doesn't already exist. Idempotent."""
    client = _get_client()
    bucket = settings.S3_BUCKET_NAME
    try:
        client.head_bucket(Bucket=bucket)
        logger.debug("Bucket '%s' already exists", bucket)
    except ClientError as exc:
        error_code = int(exc.response["ResponseMetadata"]["HTTPStatusCode"])
        if error_code == 404:
            client.create_bucket(Bucket=bucket)
            logger.info("Created bucket '%s'", bucket)
        else:
            raise S3WorkspaceError(f"Failed to check bucket '{bucket}'") from exc


# ---------------------------------------------------------------------------
# Artifact operations
# ---------------------------------------------------------------------------


def _artifact_key(artifact_id: str, version_number: int, file_path: str) -> str:
    return f"artifacts/{artifact_id}/v{version_number}/{file_path}"


def _artifact_prefix(artifact_id: str, version_number: int) -> str:
    return f"artifacts/{artifact_id}/v{version_number}/"


def upload_artifact_file(
    artifact_id: str,
    version_number: int,
    file_path: str,
    content: bytes,
) -> str:
    """
    Upload a single file for an artifact version.

    Returns the full S3 key that was written.
    """
    client = _get_client()
    key = _artifact_key(artifact_id, version_number, file_path)
    content_type = _guess_content_type(file_path)

    try:
        client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
    except ClientError as exc:
        raise S3WorkspaceError(
            f"Failed to upload artifact file '{key}'"
        ) from exc

    logger.debug("Uploaded artifact file: %s (%d bytes)", key, len(content))
    return key


def download_artifact_file(
    artifact_id: str,
    version_number: int,
    file_path: str,
) -> bytes:
    """Download a single file from an artifact version."""
    client = _get_client()
    key = _artifact_key(artifact_id, version_number, file_path)

    try:
        response = client.get_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
        )
        return response["Body"].read()
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "NoSuchKey":
            raise S3FileNotFoundError(
                f"Artifact file not found: '{key}'"
            ) from exc
        raise S3WorkspaceError(
            f"Failed to download artifact file '{key}'"
        ) from exc


def delete_artifact_version(artifact_id: str, version_number: int) -> int:
    """
    Delete all files under an artifact version prefix.

    Returns the number of objects deleted.
    """
    prefix = _artifact_prefix(artifact_id, version_number)
    return _delete_prefix(prefix)


# ---------------------------------------------------------------------------
# Document operations
# ---------------------------------------------------------------------------


def _document_key(document_id: str, filename: str) -> str:
    return f"documents/{document_id}/{filename}"


def _document_prefix(document_id: str) -> str:
    return f"documents/{document_id}/"


def upload_document(
    document_id: str,
    filename: str,
    file_bytes: bytes,
) -> str:
    """
    Upload a document file.

    Returns the full S3 key that was written.
    """
    client = _get_client()
    key = _document_key(document_id, filename)
    content_type = _guess_content_type(filename)

    try:
        client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
    except ClientError as exc:
        raise S3WorkspaceError(
            f"Failed to upload document '{key}'"
        ) from exc

    logger.debug("Uploaded document: %s (%d bytes)", key, len(file_bytes))
    return key


def download_document(document_id: str, filename: str) -> bytes:
    """Download a document file."""
    client = _get_client()
    key = _document_key(document_id, filename)

    try:
        response = client.get_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
        )
        return response["Body"].read()
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "NoSuchKey":
            raise S3FileNotFoundError(
                f"Document not found: '{key}'"
            ) from exc
        raise S3WorkspaceError(
            f"Failed to download document '{key}'"
        ) from exc


def delete_document(document_id: str) -> int:
    """
    Delete all files under a document prefix.

    Returns the number of objects deleted.
    """
    prefix = _document_prefix(document_id)
    return _delete_prefix(prefix)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_files(prefix: str) -> list[str]:
    """
    List all object keys under a given prefix.

    Handles pagination for prefixes with more than 1000 objects.
    """
    client = _get_client()
    keys: list[str] = []

    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=settings.S3_BUCKET_NAME,
            Prefix=prefix,
        ):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
    except ClientError as exc:
        raise S3WorkspaceError(
            f"Failed to list objects under prefix '{prefix}'"
        ) from exc

    return keys


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _delete_prefix(prefix: str) -> int:
    """List all objects under a prefix and batch-delete them. Returns count."""
    client = _get_client()
    keys = list_files(prefix)

    if not keys:
        return 0

    # S3 DeleteObjects supports up to 1000 keys per request
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = keys[i : i + 1000]
        delete_payload = {"Objects": [{"Key": k} for k in batch], "Quiet": True}
        try:
            client.delete_objects(
                Bucket=settings.S3_BUCKET_NAME,
                Delete=delete_payload,
            )
            deleted += len(batch)
        except ClientError as exc:
            raise S3WorkspaceError(
                f"Failed to delete objects under prefix '{prefix}'"
            ) from exc

    logger.info("Deleted %d objects under prefix '%s'", deleted, prefix)
    return deleted


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class S3WorkspaceError(Exception):
    """Base exception for S3 workspace operations."""


class S3FileNotFoundError(S3WorkspaceError):
    """Raised when a requested S3 object does not exist."""
