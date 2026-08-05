import { writable } from 'svelte/store';
import type { AuthMe } from '$lib/api/auth';

/** The resolved session for this page load — set once by the layout guard, read by the
 *  nav and the admin page so nothing re-fetches `/api/auth/me` for itself. */
export const currentUser = writable<AuthMe | null>(null);
