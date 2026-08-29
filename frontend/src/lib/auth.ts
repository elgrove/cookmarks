import { get, writable } from 'svelte/store';
import { type AuthMe, type BookGridDensity, updatePreferences } from '$lib/api/auth';

const STORAGE_KEY = 'cookmarks-book-grid-density';
const isBrowser = typeof window !== 'undefined';

function readStoredDensity(): BookGridDensity {
	if (!isBrowser) return 'standard';
	const val = localStorage.getItem(STORAGE_KEY);
	return val === 'sparse' || val === 'compact' || val === 'standard' ? val : 'standard';
}

/** The resolved session for this page load — set once by the layout guard, read by the
 *  nav and the admin page so nothing re-fetches `/api/auth/me` for itself. */
export const currentUser = writable<AuthMe | null>(null);

/** Read active density from currentUser or localStorage fallback. */
export function getBookGridDensity(): BookGridDensity {
	const user = get(currentUser);
	if (user?.book_grid_density) return user.book_grid_density;
	return readStoredDensity();
}

/** Update density optimistically in store, in backend profile if logged in, and localStorage. */
export async function setBookGridDensity(density: BookGridDensity): Promise<void> {
	if (isBrowser) {
		localStorage.setItem(STORAGE_KEY, density);
	}
	const user = get(currentUser);
	if (user) {
		currentUser.set({ ...user, book_grid_density: density });
		try {
			await updatePreferences({ book_grid_density: density });
		} catch (err) {
			console.error('failed to persist book_grid_density preference', err);
		}
	}
}
