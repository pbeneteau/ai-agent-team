# Performance Baseline Report

Generated: 2026-03-29T17:47:17.336133+00:00

| Metric | p95 (ms) | Target | Status |
|--------|----------|--------|--------|
| GET /api/roster | 0.91 | <100ms | PASS |
| GET /api/artifacts/{id} | 0.74 | <100ms | PASS |
| GET /api/artifacts/{id}/status | 0.97 | <50ms | PASS |
| File proxy (50KB) | 0.93 | <200ms | PASS |
| Sufficiency check (mocked LLM) | 1.46 | <4000ms | PASS |
| Delegate preview (mocked router) | 1.32 | <2000ms | PASS |

## Notes

- All measurements use TestClient (in-process, no network) with mocked DB
- LLM calls are mocked with deterministic responses
- Real-world latency will be higher due to network + DB + LLM round-trips
- Target thresholds from TDD-03 Section 1.2 and TDD-05 Section 20
