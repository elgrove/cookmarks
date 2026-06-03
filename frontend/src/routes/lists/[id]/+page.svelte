<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import ListDetail, { type ListDetailData } from '$lib/components/ListDetail.svelte';
	import {
		deleteList,
		fetchListDetail,
		removeRecipeFromList,
		renameList
	} from '$lib/api/lists';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let list = $state<ListDetailData | null>(null);
	let seq = 0;

	async function load(id: string) {
		const mine = ++seq;
		if (!list) status = 'loading';
		try {
			const d = await fetchListDetail(id);
			if (mine !== seq) return;
			list = {
				id: d.id,
				name: d.name,
				isDefault: d.is_default,
				recipeCount: d.recipe_count,
				recipes: d.recipes.map((r) => ({
					id: r.id,
					name: r.name,
					bookId: r.book_id,
					bookTitle: r.book_title,
					bookAuthor: r.book_author,
					keywords: r.keywords
				}))
			};
			status = 'ready';
		} catch (err) {
			if (mine !== seq) return;
			console.error('failed to load list', err);
			if (!list) status = 'error';
		}
	}

	async function rename(name: string) {
		const id = $page.params.id;
		if (!id) return;
		try {
			await renameList(id, name);
			await load(id);
		} catch (err) {
			console.error('failed to rename list', err);
		}
	}

	async function remove() {
		const id = $page.params.id;
		if (!id) return;
		try {
			await deleteList(id);
			goto('/lists');
		} catch (err) {
			console.error('failed to delete list', err);
		}
	}

	async function removeRecipe(recipeId: string) {
		const id = $page.params.id;
		if (!id) return;
		try {
			await removeRecipeFromList(id, recipeId);
			await load(id);
		} catch (err) {
			console.error('failed to remove recipe from list', err);
		}
	}

	$effect(() => {
		const id = $page.params.id;
		if (id) load(id);
		else status = 'error';
	});
</script>

{#if list}
	<ListDetail {list} onRename={rename} onDelete={remove} onRemoveRecipe={removeRecipe} />
{:else if status === 'loading'}
	<div class="status"><p class="msg">Loading list…</p></div>
{:else}
	<div class="status">
		<p class="msg">Couldn’t load this list.</p>
		<button class="retry" onclick={() => load($page.params.id ?? '')}>Try again</button>
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
