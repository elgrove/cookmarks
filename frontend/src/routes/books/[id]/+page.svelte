<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import BookDetail, { type BookDetailData } from '$lib/components/BookDetail.svelte';
	import { deleteBook, fetchBookDetail, markBookRead, resetBookProgress } from '$lib/api/books';
	import { queueBook, unqueueBook } from '$lib/api/reading-queue';
	import { cleanTitle, pageTitle } from '$lib/title';
	import { currentUser } from '$lib/auth';
	import {
		fetchLatestRun,
		resumeExtraction,
		triggerExtraction,
		type TaskRun,
		type ReviewAnswer,
		type ReviewQuestion
	} from '$lib/api/task-runs';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let book = $state<BookDetailData | null>(null);
	let latestRun = $state<TaskRun | null>(null);

	// Only a run paused at review surfaces a question; everything else shows nothing.
	let review = $derived<ReviewQuestion | null>(
		latestRun?.status === 'review' ? latestRun.pending_question : null
	);

	async function loadLatestRun(id: string) {
		try {
			latestRun = await fetchLatestRun(id);
		} catch (err) {
			// A missing run view must never break the book page; just show no prompt.
			console.error('failed to load latest extraction run', err);
			latestRun = null;
		}
	}

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
				keywords: b.keywords,
				recipes: b.recipes.map((r) => ({
					id: r.id,
					name: r.name,
					keywords: r.keywords
				})),
				queued: b.queued,
				reading: b.reading
					? {
							mode: b.reading.mode,
							fraction: b.reading.fraction,
							finished: b.reading.finished
						}
					: null,
				resumeRecipe: b.resume_recipe
			};
			status = 'ready';
			void loadLatestRun(id);
		} catch (err) {
			console.error('failed to load book', err);
			status = 'error';
		}
	}

	// Finishing or resetting paints immediately, then reloads from the server: the
	// percentage and both mode actions move together off the one change.
	async function setBookRead(read: boolean) {
		if (!book) return;
		const id = book.id;
		book.reading = read
			? { mode: book.reading?.mode ?? 'book', fraction: 1, finished: true }
			: null;
		try {
			if (read) await markBookRead(id);
			else await resetBookProgress(id);
		} catch (err) {
			console.error('failed to change book read state', err);
		}
		await load();
	}

	// The server's returned state is authoritative — the button label follows it.
	async function toggleQueue() {
		if (!book) return;
		try {
			const state = book.queued ? await unqueueBook(book.id) : await queueBook(book.id);
			book.queued = state.queued;
		} catch (err) {
			console.error('failed to toggle reading queue', err);
		}
	}

	async function answerReview(value: string) {
		if (!book || !latestRun) return;
		const run = latestRun;
		await resumeExtraction(book.id, run.id, value as ReviewAnswer);
		// Fire-and-forget: there's no live view, so clear the prompt optimistically —
		// the run is now resuming on the worker.
		latestRun = null;
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
		review={$currentUser?.is_admin ? review : null}
		onAnswer={answerReview}
		onMarkBookRead={() => setBookRead(true)}
		onResetProgress={() => setBookRead(false)}
		onToggleQueue={toggleQueue}
		onExtract={$currentUser?.is_admin
			? async () => {
					await triggerExtraction(book!.id);
				}
			: undefined}
		onDelete={$currentUser?.is_admin
			? async ({ exclude }) => {
					await deleteBook(book!.id, { exclude });
					await goto('/books');
				}
			: undefined}
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
