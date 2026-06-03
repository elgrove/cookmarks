// Matches a heading from the book's rendered text to one of the recipes we extracted from it.
// Pure + dependency-free so it unit-tests in plain vitest (no SvelteKit, no DOM).
import type { RecipeIndexEntry } from '$lib/api/books';

export type RecipeMatch = { id: string; name: string; isFavourite: boolean };
export type RecipeNameIndex = Map<string, RecipeMatch>;

/** Normalise a title/heading for comparison: lowercase, strip accents + apostrophes, drop a
 *  leading "Chapter N:" / numbering prefix, reduce everything else to single-spaced alphanumerics. */
export function normaliseTitle(raw: string): string {
	return raw
		.normalize('NFKD')
		.replace(/[̀-ͯ]/g, '') // strip diacritics
		.toLowerCase()
		.replace(/['’`]/g, '') // "rosetta's" -> "rosettas"
		.replace(/&/g, ' and ')
		.replace(/^\s*(chapter|part)\b[^:.–-]*[:.–-]\s*/, '') // "Chapter Three: "
		.replace(/^\s*\d+\s*[.):–-]\s*/, '') // leading "12. " / "12) "
		.replace(/[^a-z0-9]+/g, ' ')
		.trim()
		.replace(/\s+/g, ' ');
}

/** Index the book's recipes by normalised name. First writer wins on collision (book order),
 *  so duplicate-named recipes resolve stably to the earliest. */
export function buildRecipeIndex(recipes: RecipeIndexEntry[]): RecipeNameIndex {
	const index: RecipeNameIndex = new Map();
	for (const r of recipes) {
		const key = normaliseTitle(r.name);
		if (key && !index.has(key)) {
			index.set(key, { id: r.id, name: r.name, isFavourite: r.is_favourite });
		}
	}
	return index;
}

// Below this normalised length a prefix match is too generic to trust.
const MIN_FUZZY_LEN = 8;

/** Find the recipe a heading refers to: exact normalised match first, then a conservative
 *  whole-phrase prefix match (heading carries a trailing qualifier, or vice-versa). Returns null
 *  rather than guess — a wrong favourite is worse than a missed one. */
export function matchHeading(heading: string, index: RecipeNameIndex): RecipeMatch | null {
	const key = normaliseTitle(heading);
	if (!key) return null;

	const exact = index.get(key);
	if (exact) return exact;

	if (key.length >= MIN_FUZZY_LEN) {
		for (const [name, match] of index) {
			if (name.length < MIN_FUZZY_LEN) continue;
			if (key.startsWith(name + ' ') || name.startsWith(key + ' ')) return match;
		}
	}
	return null;
}
