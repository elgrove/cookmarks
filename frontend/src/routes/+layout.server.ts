import type { LayoutServerLoad } from "./$types";
import { auth as authApi } from "$api";
import { isApiError } from "$api/client";

export const load: LayoutServerLoad = async ({ fetch, url }) => {
  // We always need to know whether NO_AUTH is on (drives login UI)
  const config = await authApi.config({ fetch });

  let user = null;
  try {
    user = await authApi.me({ fetch });
  } catch (e) {
    if (!isApiError(e) || e.status !== 401) throw e;
  }

  // If auth is required and we have no user, redirect to /login (except when
  // we're already on /login).
  if (!config.no_auth && !user && url.pathname !== "/login") {
    return { user: null, noAuth: false, requireLogin: true };
  }

  return { user, noAuth: config.no_auth, requireLogin: false };
};
