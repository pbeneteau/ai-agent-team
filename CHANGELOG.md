# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Add `docs/ARCHITECTURE.md` with a comprehensive system-level architecture overview covering module map, technology stack, key architectural patterns (agent orchestration loop, event-driven run streaming, shared type contracts), module dependency graph, deployment topology, cross-cutting concerns, and an index of Architecture Decision Records (ADR-001 through ADR-007).
- Document `frontend/AGENTS.md` and `frontend/CLAUDE.md` in the root `README.md` directory tree.

---

## [0.1.1] - 2026-03-29

### Added

- Restore `frontend/AGENTS.md` with guidance for AI agents noting that this version of Next.js may differ significantly from training data and directing agents to read the bundled docs before writing code.
- Restore `frontend/CLAUDE.md` as a pointer to `AGENTS.md` for Claude-based tooling.

---

## [0.1.0] - 2026-03-29

### Changed

- Update end-to-end performance baseline report with latest benchmark results. All tracked endpoints continue to pass their targets, with p95 latencies improved across the board (e.g. `GET /api/roster` down from 1.17 ms to 0.91 ms, sufficiency check down from 1.88 ms to 1.46 ms).

---

[Unreleased]: ../../compare/v0.1.1...HEAD
[0.1.1]: ../../compare/v0.1.0...v0.1.1
[0.1.0]: ../../releases/tag/v0.1.0