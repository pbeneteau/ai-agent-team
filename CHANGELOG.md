# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed

- Convert the `frontend` directory from a git submodule to a regular tracked directory, making it easier to develop and review frontend changes within the main repository without requiring submodule initialization.

---

## [0.1.0] - 2026-03-29

### Changed

- Update end-to-end performance baseline report with latest benchmark results. All tracked endpoints continue to pass their targets, with p95 latencies improved across the board (e.g. `GET /api/roster` down from 1.17 ms to 0.91 ms, sufficiency check down from 1.88 ms to 1.46 ms).

---

[Unreleased]: ../../compare/v0.1.0...HEAD
[0.1.0]: ../../releases/tag/v0.1.0