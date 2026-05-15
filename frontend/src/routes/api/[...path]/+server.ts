import type { RequestHandler } from "./$types";

const API_URL = process.env.API_URL || "http://localhost:8765";

async function proxy(request: Request, path: string): Promise<Response> {
  const url = new URL(request.url);
  const target = `${API_URL}/api/${path}${url.search}`;
  const headers = new Headers(request.headers);
  // Strip host-specific headers so the backend doesn't confuse them
  headers.delete("host");
  headers.delete("content-length");

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const respHeaders = new Headers(upstream.headers);
  // Let the browser receive Set-Cookie etc. unchanged.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: respHeaders,
  });
}

export const GET: RequestHandler = ({ request, params }) =>
  proxy(request, params.path);
export const POST: RequestHandler = ({ request, params }) =>
  proxy(request, params.path);
export const PUT: RequestHandler = ({ request, params }) =>
  proxy(request, params.path);
export const PATCH: RequestHandler = ({ request, params }) =>
  proxy(request, params.path);
export const DELETE: RequestHandler = ({ request, params }) =>
  proxy(request, params.path);
