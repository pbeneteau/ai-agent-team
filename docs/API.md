# API Reference

> Complete reference for the public API surface of **alembic**. Each module has its own detailed page.

---

## Table of Contents

- [Quick Reference](#quick-reference)
- [Modules](#modules)
- [Getting Started](#getting-started)
- [Common Patterns](#common-patterns)
- [Shared Types](#shared-types)
- [Error Handling Conventions](#error-handling-conventions)

---

## Quick Reference

The most commonly used exports at a glance:

| Export | Module | Description |
|--------|--------|-------------|
| `createApp` | [`app`](./docs/api/app.md) | Initialises and returns the configured application instance. |
| `render` | [`components`](./docs/api/components.md) | Renders a UI component into the target DOM node. |
| `runMigrations` | [`alembic`](./docs/api/alembic.md) | Executes all pending database migrations in order. |

---

## Modules

| Module | Description | Key Exports |
|--------|-------------|-------------|
| [`alembic`](./docs/api/alembic.md) | Database migration engine — defines, tracks, and applies schema migrations. | `runMigrations`, `createMigration`, `rollback` |
| [`app`](./docs/api/app.md) | Application bootstrap and lifecycle management — initialises configuration, middleware, and the server. | `createApp`, `startApp`, `stopApp` |
| [`components`](./docs/api/components.md) | Reusable UI component library — presentational and container components. | `render`, `Button`, `Modal`, `Form` |
| [`e2e`](./docs/api/e2e.md) | End-to-end test harness — helpers and fixtures for browser-level integration tests. | `setup`, `teardown`, `visit`, `expect` |
| [`features`](./docs/api/features.md) | Feature-flag and domain feature modules — encapsulated business-logic slices. | `isEnabled`, `registerFeature`, `withFeature` |
| [`lib`](./docs/api/lib.md) | Shared internal utilities and helpers used across all other modules. | `logger`, `httpClient`, `formatDate` |
| [`public`](./docs/api/public.md) | Static asset manifest and public-path utilities — resolves URLs to versioned assets. | `assetUrl`, `manifest`, `publicPath` |
| [`scripts`](./docs/api/scripts.md) | Build, code-generation, and maintenance CLI scripts intended for developer tooling. | `build`, `seed`, `generate` |
| [`tests`](./docs/api/tests.md) | Unit and integration test utilities — shared mocks, factories, and assertion helpers. | `createMock`, `factory`, `renderWithProviders` |

---

## Getting Started

### Installation

```bash
npm install alembic
```

### Basic Import

```typescript
import { createApp } from 'alembic/app';
```

### Minimal Working Example

A self-contained example that demonstrates the most common entry point:

```typescript
import { createApp, startApp } from 'alembic/app';
import { runMigrations } from 'alembic/alembic';

async function main() {
  // Apply any outstanding schema migrations before boot
  await runMigrations();

  // Create and start the application
  const app = createApp({ env: process.env.NODE_ENV ?? 'development' });
  await startApp(app, { port: 3000 });

  console.log('Application running on http://localhost:3000');
}

main().catch(console.error);
```

---

## Common Patterns

Patterns that apply across multiple modules. Understanding these will make the per-module documentation easier to follow.

### Async / Await Lifecycle Hooks

Every module that owns a resource (database connections, HTTP listeners, background workers) exposes an async `setup` / `teardown` pair. Always `await` teardown during graceful shutdown to avoid resource leaks.

```typescript
import { startApp, stopApp } from 'alembic/app';

const app = await startApp(config);

process.on('SIGTERM', async () => {
  await stopApp(app);
  process.exit(0);
});
```

### Option-Object Configuration

Functions with more than two parameters accept a single options object rather than positional arguments. All option keys are optional unless marked required in the per-module documentation. This makes call sites forward-compatible with new options added in minor releases.

```typescript
// Preferred — named options, order-independent, easy to extend
const app = createApp({
  env: 'production',
  port: 8080,
  logLevel: 'warn',
});

// Avoid — positional arguments are not supported
// createApp('production', 8080, 'warn'); // ❌
```

---

## Shared Types

Types and interfaces used across multiple modules. Module-specific types are documented in their respective pages.

```typescript
/**
 * Execution environment the application is running in.
 */
type Environment = 'development' | 'test' | 'production';

/**
 * Standardised paginated response envelope returned by list endpoints.
 */
interface PaginatedResult<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
}

/**
 * Generic async operation result — avoids throwing for expected failures.
 */
type Result<T, E = AlembicError> =
  | { ok: true; value: T }
  | { ok: false; error: E };

/**
 * Lightweight logger interface implemented by the lib module and accepted
 * by any module that performs logging.
 */
interface Logger {
  debug(message: string, context?: Record<string, unknown>): void;
  info(message: string, context?: Record<string, unknown>): void;
  warn(message: string, context?: Record<string, unknown>): void;
  error(message: string, context?: Record<string, unknown>): void;
}
```

---

## Error Handling Conventions

### Error Structure

All errors thrown by this library share a consistent shape:

```typescript
interface AlembicError extends Error {
  /** Machine-readable error code for programmatic matching */
  code: string;
  /** HTTP status code, if applicable */
  statusCode?: number;
  /** Additional context about the failure */
  details?: Record<string, unknown>;
}
```

### Error Catalog

| Code | Name | Description | Module(s) |
|------|------|-------------|-----------|
| `MIGRATION_FAILED` | `MigrationFailedError` | A migration script threw or produced an irrecoverable database error. | `alembic` |
| `MIGRATION_CONFLICT` | `MigrationConflictError` | Two migrations share the same version identifier. | `alembic` |
| `APP_INIT_FAILED` | `AppInitError` | The application failed to initialise — commonly a missing required config value. | `app` |
| `FEATURE_NOT_FOUND` | `FeatureNotFoundError` | A feature flag was queried that has not been registered. | `features` |
| `ASSET_NOT_FOUND` | `AssetNotFoundError` | The requested asset path is not present in the compiled manifest. | `public` |
| `HTTP_REQUEST_FAILED` | `HttpRequestError` | An outbound HTTP request made via `lib/httpClient` received a non-2xx response. | `lib`, `features` |
| `RENDER_ERROR` | `RenderError` | A component threw during rendering and no error boundary caught it. | `components` |

### Recommended Error Handling Pattern

```typescript
import { runMigrations } from 'alembic/alembic';
import type { AlembicError } from 'alembic/lib';

async function safeMigrate() {
  try {
    await runMigrations();
  } catch (err) {
    const error = err as AlembicError;

    // Match on the stable, machine-readable code — never on error.message
    switch (error.code) {
      case 'MIGRATION_FAILED':
        console.error('Migration failed. Details:', error.details);
        process.exit(1);

      case 'MIGRATION_CONFLICT':
        console.error(
          'Conflicting migration versions detected.',
          error.details,
        );
        process.exit(1);

      default:
        // Re-throw anything unexpected so it surfaces clearly
        throw error;
    }
  }
}
```

Consumers should match on `error.code` for programmatic handling. Error messages may change between patch versions and should not be parsed.