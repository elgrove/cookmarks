<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import RecipeDetail, { type RecipeDetailData } from '$lib/components/RecipeDetail.svelte';
	import { fetchRecipeDetail } from '$lib/api/recipes';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let recipe = $state<RecipeDetailData | null>(null);

	async function load() {
		status = 'loading';
		const id = $page.params.id;
		if (!id) {
			status = 'error';
			return;
		}
		try {
			const r = await fetchRecipeDetail(id);
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
				hasImage: r.has_image
			};
			status = 'ready';
		} catch (err) {
			console.error('failed to load recipe', err);
			status = 'error';
		}
	}

	onMount(load);
</script>

{#if status === 'ready' && recipe}
	<RecipeDetail {recipe} />
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading recipe…</p>
		{:else}
			<p class="msg">Couldn’t load this recipe.</p>
			<button class="retry" onclick={load}>Try again</button>
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
