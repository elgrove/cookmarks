import { get, writable } from 'svelte/store';

export type ThemePref = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'cookmarks-theme';
const isBrowser = typeof window !== 'undefined';

function media(): MediaQueryList | null {
	return isBrowser && typeof window.matchMedia === 'function'
		? window.matchMedia('(prefers-color-scheme: dark)')
		: null;
}

function systemTheme(): ResolvedTheme {
	return media()?.matches ? 'dark' : 'light';
}

function readPref(): ThemePref {
	if (!isBrowser) return 'system';
	const v = localStorage.getItem(STORAGE_KEY);
	return v === 'light' || v === 'dark' ? v : 'system';
}

function resolve(pref: ThemePref): ResolvedTheme {
	return pref === 'system' ? systemTheme() : pref;
}

/** The user's stored preference (light/dark, or "system" to follow the OS). */
export const preference = writable<ThemePref>(readPref());

/** The theme actually in effect — what the toggle's icon reflects. */
export const resolvedTheme = writable<ResolvedTheme>(resolve(get(preference)));

function apply(theme: ResolvedTheme): void {
	resolvedTheme.set(theme);
	if (isBrowser) document.documentElement.dataset.theme = theme;
}

/** Persist preference changes and follow the OS while preference is "system".
 *  Call once on mount; the no-flash script in app.html has already set the
 *  initial data-theme, so this re-applies the same value and wires the listeners. */
export function initTheme(): void {
	if (!isBrowser) return;

	preference.subscribe((pref) => {
		if (pref === 'system') localStorage.removeItem(STORAGE_KEY);
		else localStorage.setItem(STORAGE_KEY, pref);
		apply(resolve(pref));
	});

	media()?.addEventListener('change', () => {
		if (get(preference) === 'system') apply(systemTheme());
	});
}

export function setPreference(pref: ThemePref): void {
	preference.set(pref);
}

/** Flip between light and dark, pinning an explicit choice (drops "system"). */
export function toggleTheme(): void {
	preference.set(get(resolvedTheme) === 'dark' ? 'light' : 'dark');
}
