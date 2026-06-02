<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import RecipeDetail, { type RecipeDetailData } from '$lib/components/RecipeDetail.svelte';
	import { fetchRecipeDetail } from '$lib/api/recipes';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let recipe = $state<RecipeDetailData | null>(null);

	// The forward-carried context: the page's query params with a context ensured.
	function contextQueryOf(params: URLSearchParams): string {
		const p = new URLSearchParams(params);
		if (!p.get('context')) p.set('context', 'book');
		return p.toString();
	}

	async function load(id: string, params: URLSearchParams) {
		status = 'loading';
		try {
			const contextQuery = contextQueryOf(params);
			const r = await fetchRecipeDetail(id, fetch, contextQuery);
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
				context: r.context,
				contextQuery,
				searchHref,
				previous: r.previous,
				next: r.next
			};
			status = 'ready';
		} catch (err) {
			console.error('failed to load recipe', err);
			status = 'error';
		}
	}

	// Reload whenever the id or context query changes — prev/next reuses this route.
	$effect(() => {
		const id = $page.params.id;
		const params = $page.url.searchParams;
		if (id) load(id, params);
		else status = 'error';
	});

	function retry() {
		const id = $page.params.id;
		if (id) load(id, $page.url.searchParams);
	}

	// ← / → page through the current ordering (ignored while typing in a field).
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
		}
	}

	onMount(() => {
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});
</script>

{#if status === 'ready' && recipe}
	<RecipeDetail {recipe} />
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading recipe…</p>
		{:else}
			<p class="msg">Couldn’t load this recipe.</p>
			<button class="retry" onclick={retry}>Try again</button>
		{/if}
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
