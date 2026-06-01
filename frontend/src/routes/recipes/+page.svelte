<script lang="ts">
	import { onMount } from 'svelte';
	import RecipesSearch, { type SearchStatus } from '$lib/components/RecipesSearch.svelte';
	import { fetchBooks } from '$lib/api/books';
	import {
		fetchKeywords,
		hasCriteria,
		searchRecipes,
		type KeywordSummary,
		type RecipeSearchResults,
		type SearchCriteria
	} from '$lib/api/recipes';

	let status = $state<SearchStatus>('resting');
	let results = $state<RecipeSearchResults>({ total: 0, items: [] });
	let keywords = $state<KeywordSummary[]>([]);
	let books = $state<{ id: string; title: string }[]>([]);
	let authors = $state<string[]>([]);

	// Monotonic guard: drop stale responses so a slow earlier search can't
	// overwrite the results of a newer one.
	let seq = 0;

	async function run(criteria: SearchCriteria): Promise<void> {
		if (!hasCriteria(criteria)) {
			status = 'resting';
			results = { total: 0, items: [] };
			return;
		}
		const mine = ++seq;
		status = 'loading';
		try {
			const data = await searchRecipes(criteria);
			if (mine !== seq) return;
			results = data;
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
			// still reachable by typing (search matches keyword names too). Capped so
			// the chip block doesn't push results below the fold, especially on mobile.
			keywords = (await fetchKeywords()).slice(0, 18);
		} catch (err) {
			console.error('failed to load keywords', err);
		}
	});
</script>

<RecipesSearch {status} {results} {keywords} {books} {authors} onSearch={run} />
