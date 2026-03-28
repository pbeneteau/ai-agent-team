# Performance Baseline Report

Generated: 2026-03-27T15:37:16.681732+00:00

| Metric | p95 (ms) | Target | Status |
|--------|----------|--------|--------|
| GET /api/roster | 2.8 | <100ms | PASS |
| GET /api/artifacts/{id} | 0.94 | <100ms | PASS |
| GET /api/artifacts/{id}/status | 1.67 | <50ms | PASS |
| File proxy (50KB) | 2.16 | <200ms | PASS |
| Sufficiency check (mocked LLM) | 1.82 | <4000ms | PASS |
| Delegate preview (mocked router) | 2.01 | <2000ms | PASS |

## Notes

- All measurements use TestClient (in-process, no network) with mocked DB
- LLM calls are mocked with deterministic responses
- Real-world latency will be higher due to network + DB + LLM round-trips
- Target thresholds from TDD-03 Section 1.2 and TDD-05 Section 20
