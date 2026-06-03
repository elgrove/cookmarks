<script lang="ts">
	import { onMount } from 'svelte';
	import ListsIndex from '$lib/components/ListsIndex.svelte';
	import {
		createList,
		deleteList,
		fetchLists,
		renameList,
		type ListSummary
	} from '$lib/api/lists';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let lists = $state<ListSummary[]>([]);

	async function load() {
		status = 'loading';
		try {
			lists = await fetchLists();
			status = 'ready';
		} catch (err) {
			console.error('failed to load lists', err);
			status = 'error';
		}
	}

	// Mutations re-read the lists so counts and ordering stay authoritative.
	async function create(name: string) {
		try {
			await createList(name);
			await load();
		} catch (err) {
			console.error('failed to create list', err);
		}
	}

	async function rename(id: string, name: string) {
		try {
			await renameList(id, name);
			await load();
		} catch (err) {
			console.error('failed to rename list', err);
		}
	}

	async function remove(id: string) {
		try {
			await deleteList(id);
			await load();
		} catch (err) {
			console.error('failed to delete list', err);
		}
	}

	onMount(load);
</script>

{#if status === 'ready'}
	<ListsIndex {lists} onCreate={create} onRename={rename} onDelete={remove} />
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading lists…</p>
		{:else}
			<p class="msg">Couldn’t load your lists.</p>
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
