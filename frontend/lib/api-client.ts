/**
 * Base API client with typed request wrapper and error handling.
 *
 * Ref: TDD-05 Section 5.1
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function qs(params?: Record<string, unknown>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  return new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;

  const headers: Record<string, string> = {
    ...((options?.headers as Record<string, string>) ?? {}),
  };

  // Only set Content-Type for non-FormData bodies
  if (options?.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.error?.code ?? "UNKNOWN",
      body?.error?.message ?? res.statusText,
      body?.error?.details ?? {},
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export { API_BASE, qs, request };
