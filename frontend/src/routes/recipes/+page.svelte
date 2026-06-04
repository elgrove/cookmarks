<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { page } from '$app/stores';
	import { replaceState } from '$app/navigation';
	import RecipesSearch, { type SearchStatus } from '$lib/components/RecipesSearch.svelte';
	import SimilarBrowse, { type SimilarBrowseData } from '$lib/components/SimilarBrowse.svelte';
	import { fetchBookFilters } from '$lib/api/books';
	import {
		criteriaFromParams,
		criteriaToParams,
		fetchKeywords,
		fetchRecipeDetail,
		fetchSimilarRecipes,
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

	// "Similar to <recipe>" mode: when the URL carries `?similar=<id>`, this page
	// becomes a browse of that recipe's nearest neighbours (the fuller server default)
	// instead of the search UI. Reached from the recipe page's "More like this" link.
	let inSimilarMode = $derived(!!$page.url.searchParams.get('similar'));
	let similarBrowse = $state<SimilarBrowseData | null>(null);
	let similarStatus = $state<'idle' | 'loading' | 'error'>('idle');
	let browseSeq = 0;

	async function loadSimilarBrowse(id: string): Promise<void> {
		const mine = ++browseSeq;
		similarStatus = 'loading';
		try {
			// The recipe's name (for the heading) and its neighbours, in parallel.
			const [detail, sim] = await Promise.all([fetchRecipeDetail(id), fetchSimilarRecipes(id)]);
			if (mine !== browseSeq) return;
			similarBrowse = {
				recipeId: id,
				recipeName: detail.name,
				basis: sim.basis,
				recipes: sim.items.map((it) => ({
					id: it.id,
					name: it.name,
					bookId: it.book_id,
					bookTitle: it.book_title,
					bookAuthor: it.book_author,
					keywords: it.keywords
				}))
			};
			similarStatus = 'idle';
		} catch (err) {
			if (mine !== browseSeq) return;
			console.error('failed to load similar browse', err);
			similarStatus = 'error';
		}
	}

	// Enter/leave similar mode as the `similar` param changes (incl. client nav between
	// recipes). Untracked so the loader's state writes don't re-trigger the effect.
	$effect(() => {
		const sid = $page.url.searchParams.get('similar');
		untrack(() => {
			if (sid) loadSimilarBrowse(sid);
			else {
				similarBrowse = null;
				similarStatus = 'idle';
			}
		});
	});

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

	// Run a search and reflect it into page state. No URL writes — safe to call
	// during mount, before SvelteKit's router (and thus replaceState) is ready.
	async function execute(criteria: SearchCriteria): Promise<void> {
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

	// User-initiated search: mirror it in the URL, then run it.
	function run(criteria: SearchCriteria): Promise<void> {
		syncUrl(criteria);
		return execute(criteria);
	}

	onMount(() => {
		// These three requests are independent — fire them concurrently rather than
		// in series. The search in particular depends on neither the books nor the
		// keywords, so it must not wait behind them.
		fetchBookFilters()
			.then((bs) => {
				books = bs
					.map((b) => ({ id: b.id, title: b.title }))
					.sort((a, b) => a.title.localeCompare(b.title));
				authors = [...new Set(bs.map((b) => b.author))].sort((a, b) => a.localeCompare(b));
			})
			.catch((err) => console.error('failed to load books for filters', err));

		// Show the most-used keywords as quick filter chips; rarer keywords are still
		// reachable by typing (search matches keyword names too). Once a search is
		// active these give way to co-occurrence facets. The component clamps the
		// rendered chips to a few lines, so 50 is a generous pool.
		fetchKeywords(50)
			.then((kw) => {
				globalKeywords = kw;
				// Reflect into the visible chips only while resting — an active search
				// owns the chips (its co-occurrence facets), and now that this resolves
				// concurrently it could otherwise clobber them.
				if (status === 'resting') keywords = kw;
			})
			.catch((err) => console.error('failed to load keywords', err));

		// Restore the search the URL describes (if any) straight away. The URL
		// already reflects these criteria, so run without syncing it back —
		// replaceState would throw this early, before the router is initialised.
		if (hasCriteria(initialCriteria)) execute(initialCriteria);
	});
</script>

{#if inSimilarMode}
	{#if similarBrowse}
		<SimilarBrowse {...similarBrowse} />
	{:else if similarStatus === 'error'}
		<div class="status"><p class="msg">Couldn’t load similar recipes.</p></div>
	{:else}
		<div class="status"><p class="msg">Finding similar recipes…</p></div>
	{/if}
{:else}
	<RecipesSearch
		{status}
		{results}
		{keywords}
		{books}
		{authors}
		criteria={initialCriteria}
		onSearch={run}
	/>
{/if}

<style>
	.status {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 4rem var(--page-h);
	}
	.msg {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.4rem;
		color: var(--muted);
		margin: 0;
	}
</style>
