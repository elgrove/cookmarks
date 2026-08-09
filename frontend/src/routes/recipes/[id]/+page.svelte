<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import RecipeDetail, { type RecipeDetailData } from '$lib/components/RecipeDetail.svelte';
	import SimilarRecipes, {
		type SimilarRecipesData
	} from '$lib/components/SimilarRecipes.svelte';
	import { fetchRecipeDetail, fetchSimilarRecipes, markRecipeSeen } from '$lib/api/recipes';
	import { reportReading } from '$lib/api/books';
	import {
		addRecipeToList,
		createList,
		fetchRecipeLists,
		removeRecipeFromList,
		toggleFavourite,
		type ListMembership
	} from '$lib/api/lists';
	import { pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let recipe = $state<RecipeDetailData | null>(null);
	// List memberships for the add-to-list control, loaded alongside the recipe.
	let memberships = $state<ListMembership[] | undefined>(undefined);
	// Similar recipes, fetched lazily after the page paints (KNN is off the critical
	// path); undefined until they arrive, so the section only appears once loaded.
	let similar = $state<SimilarRecipesData | undefined>(undefined);
	// Monotonic guard so a slow earlier fetch can't overwrite a newer navigation.
	let seq = 0;

	// The forward-carried context: the page's query params with a context ensured.
	function contextQueryOf(params: URLSearchParams): string {
		const p = new URLSearchParams(params);
		if (!p.get('context')) p.set('context', 'book');
		return p.toString();
	}

	// Refresh the add-to-list memberships and keep the favourite star in step with
	// the default list. Guarded by the recipe id so a stale fetch can't apply.
	async function refreshMemberships(id: string) {
		const m = await fetchRecipeLists(id);
		if (!recipe || recipe.id !== id) return;
		memberships = m;
		const def = m.find((l) => l.is_default);
		if (def) recipe.isFavourite = def.contains;
	}

	// Load the similar-recipe neighbours. Guarded by the recipe id so a stale fetch
	// from a previous navigation can't apply to the recipe now on screen.
	// The footer shows a small slice (5); when it comes back full there are more to
	// see, so we link on to the "/recipes?similar=<id>" browse page for the full set.
	const SIMILAR_FOOTER_LIMIT = 5;

	async function refreshSimilar(id: string) {
		const r = await fetchSimilarRecipes(id, fetch, SIMILAR_FOOTER_LIMIT);
		if (!recipe || recipe.id !== id) return;
		similar = {
			basis: r.basis,
			recipes: r.items.map((it) => ({
				id: it.id,
				name: it.name,
				bookId: it.book_id,
				bookTitle: it.book_title,
				bookAuthor: it.book_author,
				keywords: it.keywords
			})),
			moreHref:
				r.items.length >= SIMILAR_FOOTER_LIMIT
					? `/recipes?similar=${encodeURIComponent(id)}`
					: undefined
		};
	}

	async function load(id: string, params: URLSearchParams) {
		const mine = ++seq;
		// Keep the current recipe on screen while the next loads (swap when ready,
		// like the old HTMX partial) — only show the loading state on a cold start.
		if (!recipe) status = 'loading';
		// Hide the add-to-list control and the similar section until this recipe's
		// own data arrives, so neither lingers from the recipe just navigated away from.
		memberships = undefined;
		similar = undefined;
		try {
			const contextQuery = contextQueryOf(params);
			// Only an explicit book context is a step through the book itself — arriving at
			// a recipe from a list or the recent index reads the recipe, not its book.
			const walkingTheBook = params.get('context') === 'book';
			const r = await fetchRecipeDetail(id, fetch, contextQuery);
			if (mine !== seq) return;
			// For a search context, the breadcrumb links back to the originating search.
			let searchHref: string | null = null;
			if (r.context === 'search') {
				const s = new URLSearchParams(params);
				s.delete('context');
				const qs = s.toString();
				searchHref = qs ? `/recipes?${qs}` : '/recipes';
			}
			recipe = {
				id: r.id,
				bookId: r.book_id,
				bookTitle: r.book_title,
				bookAuthor: r.book_author,
				bookHasCover: r.book_has_cover,
				name: r.name,
				description: r.description,
				ingredients: r.ingredients,
				instructions: r.instructions,
				yields: r.yields,
				keywords: r.keywords,
				hasImage: r.has_image,
				isFavourite: r.is_favourite,
				context: r.context,
				contextQuery,
				searchHref,
				previous: r.previous,
				next: r.next
			};
			status = 'ready';
			// Record the open — fire-and-forget, and never surfaced: kept as a record of
			// what has been looked at, not shown back as read state.
			markRecipeSeen(id).catch((err) => console.error('failed to record recipe view', err));
			// Read in its book's context, this is a step through the book itself, moving
			// the book's shared reading position to this recipe.
			if (walkingTheBook) {
				reportReading(r.book_id, { mode: 'recipes', recipe_id: id }).catch((err) =>
					console.error('failed to report reading', err)
				);
			}
			refreshMemberships(id).catch((err) =>
				console.error('failed to load list memberships', err)
			);
			refreshSimilar(id).catch((err) => console.error('failed to load similar recipes', err));
		} catch (err) {
			if (mine !== seq) return;
			console.error('failed to load recipe', err);
			// Keep any recipe already shown; only surface the error on a cold start.
			if (!recipe) status = 'error';
		}
	}

	async function onToggleFavourite() {
		if (!recipe) return;
		const id = recipe.id;
		try {
			const fav = await toggleFavourite(id);
			if (recipe && recipe.id === id) recipe.isFavourite = fav;
			await refreshMemberships(id);
		} catch (err) {
			console.error('failed to toggle favourite', err);
		}
	}

	async function onToggleList(listId: string, contains: boolean) {
		if (!recipe) return;
		const id = recipe.id;
		try {
			if (contains) await removeRecipeFromList(listId, id);
			else await addRecipeToList(listId, id);
			await refreshMemberships(id);
		} catch (err) {
			console.error('failed to update list membership', err);
		}
	}

	async function onCreateList(name: string) {
		if (!recipe) return;
		const id = recipe.id;
		try {
			const list = await createList(name);
			await addRecipeToList(list.id, id);
			await refreshMemberships(id);
		} catch (err) {
			console.error('failed to create list', err);
		}
	}

	// Reload whenever the id or context query changes — prev/next reuses this route.
	// Depend only on the route id + query string; run load() untracked so its reads
	// and writes of `recipe`/`memberships` can't feed back and re-trigger the effect.
	$effect(() => {
		const id = $page.params.id;
		const search = $page.url.search;
		untrack(() => {
			if (id) load(id, new URLSearchParams(search));
			else status = 'error';
		});
	});

	function retry() {
		const id = $page.params.id;
		if (id) load(id, $page.url.searchParams);
	}

	// ← / → page through the current ordering; F toggles the favourite. All ignored
	// while typing in a field or with a modifier held.
	function onKey(e: KeyboardEvent) {
		if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
		const t = e.target as HTMLElement | null;
		if (
			t &&
			(t.tagName === 'INPUT' ||
				t.tagName === 'TEXTAREA' ||
				t.tagName === 'SELECT' ||
				t.isContentEditable)
		)
			return;
		if (status !== 'ready' || !recipe) return;
		if (e.key === 'ArrowLeft' && recipe.previous) {
			e.preventDefault();
			goto(`/recipes/${recipe.previous.id}?${recipe.contextQuery}`);
		} else if (e.key === 'ArrowRight' && recipe.next) {
			e.preventDefault();
			goto(`/recipes/${recipe.next.id}?${recipe.contextQuery}`);
		} else if ((e.key === 'f' || e.key === 'F') && !e.repeat) {
			// F toggles the recipe's favourite state — same action as the ★ button.
			// The repeat guard stops a held key firing the toggle over and over.
			e.preventDefault();
			onToggleFavourite();
		}
	}

	onMount(() => {
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});

	const docTitle = $derived(pageTitle(recipe?.name));
</script>

<svelte:head>
	<title>{docTitle}</title>
</svelte:head>

{#if recipe}
	<!-- Remount per recipe so component-local state (cover-failed, read-more) resets,
	     but only once the next recipe's data has arrived — the old one stays until then. -->
	{#key recipe.id}
		<RecipeDetail
			{recipe}
			lists={memberships}
			{onToggleFavourite}
			{onToggleList}
			{onCreateList}
		/>
		{#if similar}
			<SimilarRecipes
					recipes={similar.recipes}
					basis={similar.basis}
					moreHref={similar.moreHref}
					listPicker={{}}
				/>
		{/if}
	{/key}
{:else if status === 'loading'}
	<div class="status"><p class="msg">Loading recipe…</p></div>
{:else}
	<div class="status">
		<p class="msg">Couldn’t load this recipe.</p>
		<button class="retry" onclick={retry}>Try again</button>
	</div>
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
		margin: 0.5rem 0 1.2rem;
	}
	.retry {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		background: var(--ink);
		color: var(--bg);
		border: none;
		border-radius: 3px;
		padding: 0.55rem 1.1rem;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
	}
	.retry:hover {
		background: var(--clay-deep);
	}
</style>
