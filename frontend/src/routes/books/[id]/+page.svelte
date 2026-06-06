<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import BookDetail, { type BookDetailData } from '$lib/components/BookDetail.svelte';
	import { fetchBookDetail } from '$lib/api/books';
	import { cleanTitle, pageTitle } from '$lib/title';
	import { triggerExtraction } from '$lib/api/extraction';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let book = $state<BookDetailData | null>(null);

	async function load() {
		status = 'loading';
		const id = $page.params.id;
		if (!id) {
			status = 'error';
			return;
		}
		try {
			const b = await fetchBookDetail(id);
			book = {
				id: b.id,
				title: b.title,
				author: b.author,
				isbn: b.isbn,
				pubdate: b.pubdate,
				description: b.description,
				recipeCount: b.recipe_count,
				hasCover: b.has_cover,
				hasEpub: b.has_epub,
				added: b.added,
				recipes: b.recipes
			};
			status = 'ready';
		} catch (err) {
			console.error('failed to load book', err);
			status = 'error';
		}
	}

	onMount(load);

	const docTitle = $derived(pageTitle(book ? cleanTitle(book.title) : undefined));
</script>

<svelte:head>
	<title>{docTitle}</title>
</svelte:head>

{#if status === 'ready' && book}
	<BookDetail
		{book}
		onExtract={async () => {
			await triggerExtraction(book!.id);
		}}
	/>
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading book…</p>
		{:else}
			<p class="msg">Couldn’t load this book.</p>
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
