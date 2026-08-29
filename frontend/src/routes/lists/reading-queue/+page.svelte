<script lang="ts">
	import { onMount } from 'svelte';
	import ReadingQueue, { type QueuedBookRow } from '$lib/components/ReadingQueue.svelte';
	import { fetchReadingQueue, unqueueBook } from '$lib/api/reading-queue';
	import { pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let books = $state<QueuedBookRow[]>([]);

	async function load() {
		status = 'loading';
		try {
			const queue = await fetchReadingQueue();
			books = queue.map((b) => ({
				id: b.id,
				title: b.title,
				author: b.author,
				hasCover: b.has_cover,
				recipeCount: b.recipe_count
			}));
			status = 'ready';
		} catch (err) {
			console.error('failed to load reading queue', err);
			status = 'error';
		}
	}

	async function remove(id: string) {
		try {
			await unqueueBook(id);
			books = books.filter((b) => b.id !== id);
		} catch (err) {
			console.error('failed to remove book from queue', err);
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>{pageTitle('Reading queue')}</title>
</svelte:head>

{#if status === 'ready'}
	<ReadingQueue {books} onRemove={remove} />
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading your queue…</p>
		{:else}
			<p class="msg">Couldn’t load your reading queue.</p>
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
		background: var(--accent-deep);
	}
</style>
