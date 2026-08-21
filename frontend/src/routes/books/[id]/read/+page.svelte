<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import EpubReader from '$lib/components/EpubReader.svelte';
	import { fetchBookDetail, type ReadingState } from '$lib/api/books';
	import { cleanTitle, pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'no-epub' | 'ready'>('loading');
	let book = $state<{
		id: string;
		title: string;
		author: string;
		reading: ReadingState | null;
	} | null>(null);

	async function load() {
		status = 'loading';
		const id = $page.params.id;
		if (!id) {
			status = 'error';
			return;
		}
		try {
			const b = await fetchBookDetail(id);
			book = { id: b.id, title: cleanTitle(b.title), author: b.author, reading: b.reading };
			status = b.has_epub ? 'ready' : 'no-epub';
		} catch (err) {
			console.error('failed to load book for reader', err);
			status = 'error';
		}
	}

	onMount(load);

	const docTitle = $derived(pageTitle(book ? `${book.title} · Reader` : 'Reader'));
</script>

<svelte:head>
	<title>{docTitle}</title>
</svelte:head>

{#if status === 'ready' && book}
	<EpubReader
		bookId={book.id}
		title={book.title}
		author={book.author}
		resume={book.reading}
		startRecipeId={$page.url.searchParams.get('at')}
	/>
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading…</p>
		{:else if status === 'no-epub'}
			<p class="msg">No EPUB is available for this book.</p>
			<a class="link" href={`/books/${$page.params.id}`}>← Back to book</a>
		{:else}
			<p class="msg">Couldn’t load this book.</p>
			<button class="retry" onclick={load}>Try again</button>
		{/if}
	</div>
{/if}

<style>
	.status {
		min-height: 100dvh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1.2rem;
		padding: 2rem;
		text-align: center;
	}
	.msg {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.4rem;
		color: var(--muted);
		margin: 0;
	}
	.link {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		color: var(--clay-deep);
		text-decoration: none;
		border-bottom: 1px solid transparent;
	}
	.link:hover {
		border-bottom-color: var(--clay);
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
