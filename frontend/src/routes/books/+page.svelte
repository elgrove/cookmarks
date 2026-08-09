<script lang="ts">
	import { onMount } from 'svelte';
	import BooksLibrary, { type LibraryBook } from '$lib/components/BooksLibrary.svelte';
	import { fetchBooks } from '$lib/api/books';
	import { fetchReadingQueue } from '$lib/api/reading-queue';
	import { pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let books = $state<LibraryBook[]>([]);

	async function load() {
		status = 'loading';
		try {
			const data = await fetchBooks();
			// Queue positions feed the "Queue order" sort; a failed fetch just means
			// no queued books lead, not a broken library.
			const positions = new Map<string, number>();
			try {
				(await fetchReadingQueue()).forEach((b, i) => positions.set(b.id, i + 1));
			} catch (err) {
				console.error('failed to load reading queue for sort', err);
			}
			books = data.map((b) => ({
				id: b.id,
				title: b.title,
				author: b.author,
				recipeCount: b.recipe_count,
				progress: b.progress,
				hasCover: b.has_cover,
				keywords: b.keywords,
				queuePosition: positions.get(b.id) ?? null
			}));
			status = 'ready';
		} catch (err) {
			console.error('failed to load books', err);
			status = 'error';
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>{pageTitle('Books')}</title>
</svelte:head>

{#if status === 'ready'}
	<BooksLibrary {books} />
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading library…</p>
		{:else}
			<p class="msg">Couldn’t load the library.</p>
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
