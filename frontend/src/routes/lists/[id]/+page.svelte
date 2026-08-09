<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import ListDetail, { type ListDetailData } from '$lib/components/ListDetail.svelte';
	import {
		bulkAddToList,
		bulkRemoveFromList,
		createList,
		deleteList,
		fetchListDetail,
		fetchLists,
		removeRecipeFromList,
		renameList,
		type ListMembership
	} from '$lib/api/lists';
	import { pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let list = $state<ListDetailData | null>(null);
	let seq = 0;

	// The selection bar's lists (ticks suppressed there — a flat mapping suffices).
	let barLists = $state<ListMembership[]>([]);

	async function loadBarLists(): Promise<void> {
		try {
			const ls = await fetchLists();
			barLists = ls.map((l) => ({
				id: l.id,
				name: l.name,
				is_default: l.is_default,
				contains: false
			}));
		} catch (err) {
			console.error('failed to load lists for selection', err);
		}
	}

	async function bulkAdd(listId: string, recipeIds: string[]): Promise<void> {
		try {
			await bulkAddToList(listId, recipeIds);
		} catch (err) {
			console.error('bulk add failed', err);
		}
	}

	async function bulkCreate(name: string, recipeIds: string[]): Promise<void> {
		try {
			const created = await createList(name);
			await bulkAddToList(created.id, recipeIds);
			await loadBarLists();
		} catch (err) {
			console.error('bulk create failed', err);
		}
	}

	async function bulkRemove(recipeIds: string[]): Promise<void> {
		const id = $page.params.id;
		if (!id) return;
		try {
			await bulkRemoveFromList(id, recipeIds);
			await load(id);
		} catch (err) {
			console.error('bulk remove failed', err);
		}
	}

	const selectionTools = $derived({
		lists: barLists,
		onAdd: bulkAdd,
		onCreate: bulkCreate,
		onRemove: bulkRemove
	});

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

	$effect(() => {
		void loadBarLists();
	});

	const docTitle = $derived(pageTitle(list?.name));
</script>

<svelte:head>
	<title>{docTitle}</title>
</svelte:head>

{#if list}
	<ListDetail
		{list}
		onRename={rename}
		onDelete={remove}
		onRemoveRecipe={removeRecipe}
		selection={selectionTools}
		listPicker={{}}
	/>
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
