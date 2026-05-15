/**
 * Hand-written API client. Keeps types close to the hand-written schemas.
 * (We could generate via openapi-typescript, but a small set of helpers is
 * lighter for this app and easier to read.)
 */

export interface ApiError extends Error {
  status: number;
  body: unknown;
}

export interface FetchOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | string[] | undefined | null>;
  fetch?: typeof fetch;
  headers?: Record<string, string>;
}

function buildQuery(params: FetchOptions["query"]): string {
  if (!params) return "";
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) qs.append(key, String(v));
    } else {
      qs.set(key, String(value));
    }
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export function apiBase(): string {
  // In the browser, calls go through the Vite dev proxy or the same origin.
  // On the server (SSR / load), use API_URL env var or fall back to localhost.
  if (typeof window === "undefined") {
    return process.env.API_URL || "http://localhost:8765";
  }
  return "";
}

export async function apiFetch<T>(
  path: string,
  opts: FetchOptions = {},
): Promise<T> {
  const f = opts.fetch ?? fetch;
  const url = `${apiBase()}/api/v1${path}${buildQuery(opts.query)}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Requested-With": "XMLHttpRequest",
    ...(opts.headers ?? {}),
  };
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const res = await f(url, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    credentials: "include",
  });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    const err = new Error(
      `API ${opts.method ?? "GET"} ${path} → ${res.status}`,
    ) as ApiError;
    err.status = res.status;
    err.body = body;
    throw err;
  }

  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return (await res.text()) as unknown as T;
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof Error && "status" in e && typeof (e as ApiError).status === "number";
}
