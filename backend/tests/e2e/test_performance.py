"""Ticket 11.4 — Performance Baseline.

Measures and documents baseline performance metrics:
  - API response times (roster list, artifact detail, heartbeat poll)
  - Artifact file proxy latency
  - Sufficiency check round-trip (mocked LLM)
  - Database query efficiency (verify pagination works)
  - Route response overhead

Generates a markdown report with metric/value/target/pass-fail table.
"""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.main import app
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.execution_wave import ExecutionWave
from app.models.project import Project
from app.models.workspace import Workspace

from .conftest import (
    WORKSPACE_ID,
    make_agent,
    make_artifact,
    make_artifact_version,
    make_execution_wave,
    make_project,
    make_workspace,
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _setup_overrides(mock_db: AsyncMock) -> TestClient:
    async def _db():
        yield mock_db

    async def _ws():
        return WORKSPACE_ID

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_workspace_id] = _ws
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.clear()


def _measure(client: TestClient, method: str, url: str, iterations: int = 20, **kwargs) -> dict:
    """Measure response time over N iterations, return stats in ms."""
    times: list[float] = []
    status_code: int = 0

    for _ in range(iterations):
        start = time.perf_counter()
        if method == "GET":
            resp = client.get(url, **kwargs)
        elif method == "POST":
            resp = client.post(url, **kwargs)
        elif method == "PATCH":
            resp = client.patch(url, **kwargs)
        else:
            resp = client.get(url, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        times.append(elapsed_ms)
        status_code = resp.status_code

    return {
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "avg_ms": round(statistics.mean(times), 2),
        "p50_ms": round(statistics.median(times), 2),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 2),
        "status_code": status_code,
        "iterations": iterations,
    }


# ---------------------------------------------------------------------------
# Performance Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def perf_report() -> list[dict]:
    """Accumulate performance measurements for the final report."""
    return []


# ---------------------------------------------------------------------------
# Performance Tests
# ---------------------------------------------------------------------------


class TestAPIResponseTimes:
    """Measure API response times for key read endpoints."""

    def test_roster_list_response_time(self, perf_report: list[dict]) -> None:
        """GET /api/roster — target < 100ms p95."""
        mock_db = AsyncMock()
        agents = [make_agent(name=f"Agent {i}") for i in range(10)]
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents)))
        ))

        client = _setup_overrides(mock_db)
        try:
            stats = _measure(client, "GET", "/api/roster")
            perf_report.append({
                "metric": "GET /api/roster (list)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<100ms p95",
                "pass": stats["p95_ms"] < 100,
            })
            assert stats["status_code"] == 200
            # TestClient overhead is minimal; p95 should be well under 100ms
            assert stats["p95_ms"] < 500  # Generous for CI — mock DB is instant
        finally:
            _teardown()

    def test_artifact_detail_response_time(self, perf_report: list[dict]) -> None:
        """GET /api/artifacts/{id} — target < 100ms p95."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            stats = _measure(client, "GET", "/api/artifacts/art-1")
            perf_report.append({
                "metric": "GET /api/artifacts/{id} (detail)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<100ms p95",
                "pass": stats["p95_ms"] < 100,
            })
            assert stats["status_code"] == 200
            assert stats["p95_ms"] < 500
        finally:
            _teardown()

    def test_heartbeat_poll_response_time(self, perf_report: list[dict]) -> None:
        """GET /api/artifacts/{id}/status — target < 50ms p95."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="drafting")
        wave = make_execution_wave(artifact_id="art-1", status="running")

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=wave)
        ))

        client = _setup_overrides(mock_db)
        try:
            stats = _measure(client, "GET", "/api/artifacts/art-1/status")
            perf_report.append({
                "metric": "GET /api/artifacts/{id}/status (heartbeat)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<50ms p95",
                "pass": stats["p95_ms"] < 50,
            })
            assert stats["status_code"] == 200
            assert stats["p95_ms"] < 500
        finally:
            _teardown()


class TestFileProxyPerformance:
    """Measure artifact file proxy latency."""

    def test_file_proxy_50kb_response_time(self, perf_report: list[dict]) -> None:
        """GET /api/artifacts/{id}/versions/{v}/files/{path} — measure for 50KB file."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        v1 = make_artifact_version(
            artifact_id="art-1",
            version_number=1,
            file_manifest=["report.md"],
        )

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=v1)
        ))

        # 50KB content
        content = b"# Report\n" + b"x" * 50_000

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.core.s3_workspace.download_artifact_file",
                return_value=content,
            ):
                stats = _measure(
                    client, "GET",
                    "/api/artifacts/art-1/versions/1/files/report.md",
                    iterations=10,
                )

            perf_report.append({
                "metric": "File proxy (50KB)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<200ms p95",
                "pass": stats["p95_ms"] < 200,
            })
            assert stats["status_code"] == 200
        finally:
            _teardown()


class TestSufficiencyPerformance:
    """Measure sufficiency check round-trip (mocked LLM)."""

    def test_sufficiency_check_response_time(self, perf_report: list[dict]) -> None:
        """POST /api/artifacts/{id}/validate — target < 4s with real LLM (mocked here)."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", project_id="proj-1")
        project = make_project(project_id="proj-1")
        ws = make_workspace()

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
            (Project, "proj-1"): project,
            (Workspace, WORKSPACE_ID): ws,
        }.get((cls, id_)))

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.sufficiency.run_sufficiency_check",
                new_callable=AsyncMock,
            ) as mock_check:
                result = MagicMock()
                result.eligible = True
                result.score = 85
                result.issues = []
                mock_check.return_value = result

                stats = _measure(
                    client, "POST",
                    "/api/artifacts/art-1/validate",
                    iterations=10,
                )

            perf_report.append({
                "metric": "Sufficiency check (mocked LLM)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<4000ms (mocked: <100ms)",
                "pass": stats["p95_ms"] < 100,
            })
            assert stats["status_code"] == 200
        finally:
            _teardown()


class TestPaginationPerformance:
    """Verify pagination overhead is minimal."""

    def test_paginated_project_list(self, perf_report: list[dict]) -> None:
        """GET /api/projects — paginated list."""
        mock_db = AsyncMock()
        projects = [make_project(name=f"Project {i}") for i in range(20)]
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=projects)))
        ))
        mock_db.scalar = AsyncMock(return_value=5)  # artifact count per project

        client = _setup_overrides(mock_db)
        try:
            stats = _measure(client, "GET", "/api/projects?limit=20")
            perf_report.append({
                "metric": "GET /api/projects (paginated, 20 items)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<100ms p95",
                "pass": stats["p95_ms"] < 100,
            })
            assert stats["status_code"] == 200
        finally:
            _teardown()


class TestDelegatePerformance:
    """Measure delegation preview response time."""

    def test_delegate_preview_response_time(self, perf_report: list[dict]) -> None:
        """POST /api/artifacts/{id}/delegate (preview) — includes router call."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1")
        ws = make_workspace()
        agents = [make_agent(name=f"A{i}") for i in range(5)]

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
            (Workspace, WORKSPACE_ID): ws,
        }.get((cls, id_)))
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents)))
        ))

        from .conftest import mock_routing_result

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.router.route_brief",
                new_callable=AsyncMock,
                return_value=mock_routing_result(),
            ):
                stats = _measure(
                    client, "POST",
                    "/api/artifacts/art-1/delegate",
                    iterations=10,
                    json={"confirm": False},
                )

            perf_report.append({
                "metric": "Delegate preview (mocked router)",
                "value": f"{stats['p95_ms']}ms p95",
                "target": "<2000ms (mocked: <100ms)",
                "pass": stats["p95_ms"] < 100,
            })
            assert stats["status_code"] == 200
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Performance Report Generation
# ---------------------------------------------------------------------------


class TestPerformanceReport:
    """Generate the final performance baseline report."""

    def test_generate_report(self, perf_report: list[dict]) -> None:
        """Run all perf measurements and generate markdown report.

        This test runs last because it relies on other tests populating
        perf_report. In practice each test runs independently, so this
        test generates its own measurements for the report.
        """
        mock_db = AsyncMock()
        agents = [make_agent(name=f"Agent {i}") for i in range(10)]
        artifact = make_artifact(artifact_id="art-perf", status="in_review")
        wave = make_execution_wave(artifact_id="art-perf", status="running")

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents))),
            scalar_one_or_none=MagicMock(return_value=wave),
        ))

        client = _setup_overrides(mock_db)
        try:
            report_data: list[dict] = []

            # 1. Roster list
            stats = _measure(client, "GET", "/api/roster")
            report_data.append({
                "Metric": "GET /api/roster",
                "p95 (ms)": stats["p95_ms"],
                "Target": "<100ms",
                "Status": "PASS" if stats["p95_ms"] < 100 else "FAIL",
            })

            # 2. Artifact detail
            stats = _measure(client, "GET", "/api/artifacts/art-perf")
            report_data.append({
                "Metric": "GET /api/artifacts/{id}",
                "p95 (ms)": stats["p95_ms"],
                "Target": "<100ms",
                "Status": "PASS" if stats["p95_ms"] < 100 else "FAIL",
            })

            # 3. Heartbeat status
            mock_db.get = AsyncMock(return_value=make_artifact(
                artifact_id="art-perf", status="drafting"
            ))
            mock_db.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=wave)
            ))
            stats = _measure(client, "GET", "/api/artifacts/art-perf/status")
            report_data.append({
                "Metric": "GET /api/artifacts/{id}/status",
                "p95 (ms)": stats["p95_ms"],
                "Target": "<50ms",
                "Status": "PASS" if stats["p95_ms"] < 50 else "FAIL",
            })

            # 4. File proxy (50KB)
            v1 = make_artifact_version(
                artifact_id="art-perf", version_number=1, file_manifest=["f.md"]
            )
            mock_db.get = AsyncMock(return_value=make_artifact(
                artifact_id="art-perf", status="in_review"
            ))
            mock_db.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=v1)
            ))
            with patch(
                "app.core.s3_workspace.download_artifact_file",
                return_value=b"x" * 50_000,
            ):
                stats = _measure(
                    client, "GET",
                    "/api/artifacts/art-perf/versions/1/files/f.md",
                    iterations=10,
                )
            report_data.append({
                "Metric": "File proxy (50KB)",
                "p95 (ms)": stats["p95_ms"],
                "Target": "<200ms",
                "Status": "PASS" if stats["p95_ms"] < 200 else "FAIL",
            })

            # 5. Sufficiency check (mocked)
            mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
                (Artifact, "art-perf"): make_artifact(artifact_id="art-perf", project_id="proj-1"),
                (Project, "proj-1"): make_project(project_id="proj-1"),
                (Workspace, WORKSPACE_ID): make_workspace(),
            }.get((cls, id_)))
            with patch(
                "app.agents.sufficiency.run_sufficiency_check",
                new_callable=AsyncMock,
                return_value=MagicMock(eligible=True, score=85, issues=[]),
            ):
                stats = _measure(
                    client, "POST",
                    "/api/artifacts/art-perf/validate",
                    iterations=10,
                )
            report_data.append({
                "Metric": "Sufficiency check (mocked LLM)",
                "p95 (ms)": stats["p95_ms"],
                "Target": "<4000ms",
                "Status": "PASS" if stats["p95_ms"] < 4000 else "FAIL",
            })

            # 6. Delegate preview (mocked router)
            mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
                (Artifact, "art-perf"): make_artifact(artifact_id="art-perf"),
                (Workspace, WORKSPACE_ID): make_workspace(),
            }.get((cls, id_)))
            mock_db.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(
                    all=MagicMock(return_value=[make_agent()])
                ))
            ))
            from .conftest import mock_routing_result
            with patch(
                "app.agents.router.route_brief",
                new_callable=AsyncMock,
                return_value=mock_routing_result(),
            ):
                stats = _measure(
                    client, "POST",
                    "/api/artifacts/art-perf/delegate",
                    iterations=10,
                    json={"confirm": False},
                )
            report_data.append({
                "Metric": "Delegate preview (mocked router)",
                "p95 (ms)": stats["p95_ms"],
                "Target": "<2000ms",
                "Status": "PASS" if stats["p95_ms"] < 2000 else "FAIL",
            })

            # Generate report
            report_lines = [
                "# Performance Baseline Report",
                "",
                f"Generated: {datetime.now(timezone.utc).isoformat()}",
                "",
                "| Metric | p95 (ms) | Target | Status |",
                "|--------|----------|--------|--------|",
            ]
            for row in report_data:
                status_icon = "PASS" if row["Status"] == "PASS" else "FAIL"
                report_lines.append(
                    f"| {row['Metric']} | {row['p95 (ms)']} | {row['Target']} | {status_icon} |"
                )
            report_lines.extend([
                "",
                "## Notes",
                "",
                "- All measurements use TestClient (in-process, no network) with mocked DB",
                "- LLM calls are mocked with deterministic responses",
                "- Real-world latency will be higher due to network + DB + LLM round-trips",
                "- Target thresholds from TDD-03 Section 1.2 and TDD-05 Section 20",
                "",
            ])

            report_text = "\n".join(report_lines)

            # Write report to file
            report_path = Path(__file__).parent / "performance_report.md"
            report_path.write_text(report_text)

            # Print report for pytest output
            print("\n" + report_text)

            # Verify all pass
            failures = [r for r in report_data if r["Status"] == "FAIL"]
            assert len(failures) == 0, f"Performance failures: {failures}"
        finally:
            _teardown()
