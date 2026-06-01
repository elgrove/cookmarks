<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { replaceState } from '$app/navigation';
	import RecipesSearch, { type SearchStatus } from '$lib/components/RecipesSearch.svelte';
	import { fetchBooks } from '$lib/api/books';
	import {
		criteriaFromParams,
		criteriaToParams,
		fetchKeywords,
		hasCriteria,
		searchRecipes,
		type KeywordSummary,
		type RecipeSearchResults,
		type SearchCriteria
	} from '$lib/api/recipes';

	// Seed the controls from the URL, so the search is shareable and survives a
	// round-trip into a recipe and back. Read window.location, not $page.url: on a
	// client back-navigation the page store lags a tick behind the real URL, which
	// would otherwise restore an empty search.
	const initialSearch = typeof window !== 'undefined' ? window.location.search : $page.url.search;
	const initialCriteria = criteriaFromParams(new URLSearchParams(initialSearch));

	let status = $state<SearchStatus>('resting');
	let results = $state<RecipeSearchResults>({ total: 0, items: [], facets: [] });
	let keywords = $state<KeywordSummary[]>([]);
	let books = $state<{ id: string; title: string }[]>([]);
	let authors = $state<string[]>([]);

	// The global most-used keywords, shown on the resting state. Cached on mount
	// so we can restore them when the search is cleared back to resting.
	let globalKeywords: KeywordSummary[] = [];

	// Monotonic guard: drop stale responses so a slow earlier search can't
	// overwrite the results of a newer one.
	let seq = 0;

	// Mirror the live criteria in the URL — one history entry that updates as you
	// search (replaceState), so leaving for a recipe and coming back restores it.
	function syncUrl(criteria: SearchCriteria): void {
		const p = criteriaToParams(criteria);
		p.delete('limit'); // constant page size — keep the URL clean
		if (!criteria.offset) p.delete('offset');
		if (criteria.sort === 'random') p.delete('sort'); // the default
		const qs = p.toString();
		replaceState(qs ? `/recipes?${qs}` : '/recipes', {});
	}

	async function run(criteria: SearchCriteria): Promise<void> {
		syncUrl(criteria);
		if (!hasCriteria(criteria)) {
			status = 'resting';
			results = { total: 0, items: [], facets: [] };
			keywords = globalKeywords;
			return;
		}
		const mine = ++seq;
		status = 'loading';
		try {
			const data = await searchRecipes(criteria);
			if (mine !== seq) return;
			results = data;
			// Re-rank the chips to the keywords that co-occur with the current
			// criteria; the component pins the selected ones on top of these.
			keywords = data.facets;
			status = data.items.length ? 'results' : 'empty';
		} catch (err) {
			if (mine !== seq) return;
			console.error('recipe search failed', err);
			status = 'error';
		}
	}

	onMount(async () => {
		try {
			const bs = await fetchBooks();
			books = bs
				.map((b) => ({ id: b.id, title: b.title }))
				.sort((a, b) => a.title.localeCompare(b.title));
			authors = [...new Set(bs.map((b) => b.author))].sort((a, b) => a.localeCompare(b));
		} catch (err) {
			console.error('failed to load books for filters', err);
		}
		try {
			// Show the most-used keywords as quick filter chips; rarer keywords are
			// still reachable by typing (search matches keyword names too). Once a
			// search is active these give way to co-occurrence facets. The component
			// clamps the rendered chips to a few lines, so hand over a generous pool.
			globalKeywords = (await fetchKeywords()).slice(0, 50);
			keywords = globalKeywords;
		} catch (err) {
			console.error('failed to load keywords', err);
		}
		// Restore the search the URL describes (if any) once the filters are loaded.
		if (hasCriteria(initialCriteria)) run(initialCriteria);
	});
</script>

<RecipesSearch
	{status}
	{results}
	{keywords}
	{books}
	{authors}
	criteria={initialCriteria}
	onSearch={run}
/>
