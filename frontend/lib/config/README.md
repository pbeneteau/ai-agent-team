# Frontend config boundaries

- `navigation.ts`, `status-meta.ts`, `formatting.ts`, `realtime.ts`, `ui-limits.ts`, `page-copy.ts`: UI/runtime policy and reusable presentation config.
- Browser-persisted product state should live in dedicated stores/contexts, not in this folder.

Do not mix deployment environment variables with reusable UX constants unless the value truly comes from `process.env`.
