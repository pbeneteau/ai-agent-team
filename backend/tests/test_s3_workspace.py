"""
Integration tests for app.core.s3_workspace.

Requires MinIO running (docker compose up minio).
"""

import uuid

import pytest

from app.core import s3_workspace
from app.core.s3_workspace import (
    S3FileNotFoundError,
    delete_artifact_version,
    delete_document,
    download_artifact_file,
    download_document,
    ensure_bucket,
    list_files,
    upload_artifact_file,
    upload_document,
)


@pytest.fixture(autouse=True)
def _setup_bucket() -> None:
    """Ensure the bucket exists before every test."""
    ensure_bucket()


def _unique_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Artifact operations
# ---------------------------------------------------------------------------


class TestArtifactUploadDownload:
    """Upload a file, download it, verify content matches."""

    def test_roundtrip_text_file(self) -> None:
        artifact_id = _unique_id()
        content = b"# Hello World\n\nThis is a test artifact."

        key = upload_artifact_file(artifact_id, 1, "README.md", content)
        assert key == f"artifacts/{artifact_id}/v1/README.md"

        downloaded = download_artifact_file(artifact_id, 1, "README.md")
        assert downloaded == content

    def test_roundtrip_binary_file(self) -> None:
        artifact_id = _unique_id()
        content = bytes(range(256))

        upload_artifact_file(artifact_id, 1, "data.bin", content)
        downloaded = download_artifact_file(artifact_id, 1, "data.bin")
        assert downloaded == content

    def test_roundtrip_nested_path(self) -> None:
        artifact_id = _unique_id()
        content = b"export const foo = 42;"

        upload_artifact_file(artifact_id, 2, "src/lib/utils.ts", content)
        downloaded = download_artifact_file(artifact_id, 2, "src/lib/utils.ts")
        assert downloaded == content

    def test_download_nonexistent_raises(self) -> None:
        with pytest.raises(S3FileNotFoundError):
            download_artifact_file("nonexistent", 1, "nope.txt")


class TestArtifactListFiles:
    """List files under an artifact prefix."""

    def test_list_returns_correct_paths(self) -> None:
        artifact_id = _unique_id()
        files = {
            "src/index.ts": b"console.log('hi');",
            "src/styles.css": b"body { margin: 0; }",
            "tests/index.test.ts": b"test('ok', () => {});",
        }

        for path, content in files.items():
            upload_artifact_file(artifact_id, 1, path, content)

        prefix = f"artifacts/{artifact_id}/v1/"
        listed = list_files(prefix)

        expected = sorted(f"{prefix}{p}" for p in files)
        assert sorted(listed) == expected

    def test_list_empty_prefix_returns_empty(self) -> None:
        result = list_files(f"artifacts/{_unique_id()}/v99/")
        assert result == []


class TestArtifactDelete:
    """Delete removes all files under the version prefix."""

    def test_delete_artifact_version(self) -> None:
        artifact_id = _unique_id()
        upload_artifact_file(artifact_id, 1, "a.txt", b"aaa")
        upload_artifact_file(artifact_id, 1, "b.txt", b"bbb")
        upload_artifact_file(artifact_id, 1, "sub/c.txt", b"ccc")

        deleted_count = delete_artifact_version(artifact_id, 1)
        assert deleted_count == 3

        prefix = f"artifacts/{artifact_id}/v1/"
        assert list_files(prefix) == []

    def test_delete_nonexistent_returns_zero(self) -> None:
        assert delete_artifact_version("nonexistent", 99) == 0

    def test_delete_one_version_keeps_other(self) -> None:
        artifact_id = _unique_id()
        upload_artifact_file(artifact_id, 1, "file.txt", b"v1")
        upload_artifact_file(artifact_id, 2, "file.txt", b"v2")

        delete_artifact_version(artifact_id, 1)

        # v2 should still exist
        assert download_artifact_file(artifact_id, 2, "file.txt") == b"v2"
        # v1 should be gone
        with pytest.raises(S3FileNotFoundError):
            download_artifact_file(artifact_id, 1, "file.txt")


# ---------------------------------------------------------------------------
# Document operations
# ---------------------------------------------------------------------------


class TestDocumentUploadDownload:
    """Upload a document, download it, verify content matches."""

    def test_roundtrip(self) -> None:
        doc_id = _unique_id()
        content = b"%PDF-1.4 fake pdf content"

        key = upload_document(doc_id, "report.pdf", content)
        assert key == f"documents/{doc_id}/report.pdf"

        downloaded = download_document(doc_id, "report.pdf")
        assert downloaded == content

    def test_download_nonexistent_raises(self) -> None:
        with pytest.raises(S3FileNotFoundError):
            download_document("nonexistent", "nope.pdf")


class TestDocumentListFiles:
    """List files under a document prefix."""

    def test_list_document_files(self) -> None:
        doc_id = _unique_id()
        upload_document(doc_id, "file.pdf", b"pdf content")

        listed = list_files(f"documents/{doc_id}/")
        assert listed == [f"documents/{doc_id}/file.pdf"]


class TestDocumentDelete:
    """Delete removes all files under the document prefix."""

    def test_delete_document(self) -> None:
        doc_id = _unique_id()
        upload_document(doc_id, "file.pdf", b"content")

        deleted_count = delete_document(doc_id)
        assert deleted_count == 1
        assert list_files(f"documents/{doc_id}/") == []

    def test_delete_nonexistent_returns_zero(self) -> None:
        assert delete_document("nonexistent") == 0


# ---------------------------------------------------------------------------
# Bucket idempotency
# ---------------------------------------------------------------------------


class TestEnsureBucket:
    """ensure_bucket() is safe to call multiple times."""

    def test_idempotent(self) -> None:
        ensure_bucket()
        ensure_bucket()  # Should not raise


# ---------------------------------------------------------------------------
# Client reset helper for test isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the module-level client between tests for clean state."""
    s3_workspace._client = None
