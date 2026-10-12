// Minimal $app/stores stand-in for route tests under plain vitest (no SvelteKit).
// Only the fields the list routes read are modelled.
import { writable } from 'svelte/store';

export const page = writable<{ params: { id?: string } }>({ params: {} });

/** Simulate a route change to another list id. */
export function setPageId(id: string): void {
	page.set({ params: { id } });
}
