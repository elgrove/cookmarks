import type { Handle } from "@sveltejs/kit";

// Forward cookies and X-Requested-With on server-side fetches so the Django
// API sees the same session as the browser. SvelteKit's load functions call
// `event.fetch` which already inherits cookies for same-origin URLs; we only
// need to set the X-Requested-With header to align with how the browser calls.
export const handle: Handle = async ({ event, resolve }) => {
  return resolve(event);
};

export const handleFetch = async ({ request, fetch }) => {
  // Ensure server-side fetches to the API include the marker header.
  if (request.url.includes("/api/")) {
    const cloned = new Request(request, {
      headers: new Headers(request.headers),
    });
    cloned.headers.set("X-Requested-With", "XMLHttpRequest");
    return fetch(cloned);
  }
  return fetch(request);
};
