<script module lang="ts">
	export type QueuedBookRow = {
		id: string;
		title: string;
		author: string;
		hasCover: boolean;
		recipeCount: number;
	};

	export type ReadingQueueProps = {
		books: QueuedBookRow[];
		onRemove?: (id: string) => void;
	};
</script>

<script lang="ts">
	import { cleanTitle } from '$lib/title';

	let { books, onRemove }: ReadingQueueProps = $props();

	// Echo of the last removal, so the harness can verify wiring in isolation.
	let lastRemoved = $state('');
	// Covers whose fetch failed fall back to the text-only row.
	let failedCovers = $state<string[]>([]);

	function remove(id: string) {
		lastRemoved = id;
		onRemove?.(id);
	}
</script>

<section
	class="queue"
	data-verify-unit="reading-queue"
	data-verify-count={books.length}
	data-verify-empty={books.length === 0 ? 'true' : 'false'}
	data-verify-removed={lastRemoved}
>
	<header class="head">
		<p class="crumb mono"><a href="/lists">Lists</a> › Reading queue</p>
		<h1 class="display">Reading queue</h1>
		<p class="count mono">
			{books.length}
			{books.length === 1 ? 'book' : 'books'} · newest first
		</p>
	</header>

	{#if books.length === 0}
		<p class="empty">Nothing queued yet.</p>
		<p class="hint">Queue a book from its page and it will wait for you here.</p>
	{:else}
		<ol class="index">
			{#each books as book, i (book.id)}
				{@const title = cleanTitle(book.title)}
				<li class="row" style={`animation-delay: ${Math.min(i * 40, 400)}ms`}>
					<span class="num mono" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
					{#if book.hasCover && !failedCovers.includes(book.id)}
						<a class="thumb" href={`/books/${book.id}`} tabindex="-1" aria-hidden="true">
							<img
								src={`/api/books/${book.id}/cover`}
								alt=""
								loading="lazy"
								onerror={() => (failedCovers = [...failedCovers, book.id])}
							/>
						</a>
					{:else}
						<span class="thumb blank" aria-hidden="true"></span>
					{/if}
					<span class="text">
						<a class="title" href={`/books/${book.id}`}>{title}</a>
						<span class="author">{book.author}</span>
					</span>
					<span class="meta mono">
						{#if book.recipeCount > 0}{book.recipeCount} recipes{:else}— pending extraction{/if}
					</span>
					<button
						class="remove"
						type="button"
						aria-label={`Remove ${title} from queue`}
						onclick={() => remove(book.id)}
					>
						Remove
					</button>
				</li>
			{/each}
		</ol>
	{/if}
</section>

<style>
	.queue {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}

	.head {
		margin-bottom: 2.25rem;
		padding-bottom: 1.25rem;
		border-bottom: var(--border);
	}
	.crumb {
		font-size: 0.72rem;
		color: var(--muted);
		margin: 0 0 0.6rem;
	}
	.crumb a {
		color: inherit;
		text-decoration: none;
	}
	.crumb a:hover {
		color: var(--clay-deep);
	}
	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3.2rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin: 0.2rem 0 0.6rem;
	}
	.count {
		color: var(--muted);
		margin: 0;
	}

	/* A numbered index of books (DESIGN §4): clay number, small cover plate where one
	   exists, title leading and the count trailing in quiet mono. */
	.index {
		list-style: none;
		margin: 0;
		padding: 0;
		max-width: 52rem;
	}
	.row {
		display: grid;
		grid-template-columns: 2.2rem 2.9rem 1fr auto auto;
		align-items: center;
		gap: 0.5rem 1rem;
		padding: 0.85rem 0;
		border-bottom: var(--border);
		animation: fadeUp 0.5s var(--ease-out) both;
	}
	.num {
		font-size: 0.72rem;
		color: var(--clay);
	}
	.thumb {
		display: block;
		width: 2.9rem;
		aspect-ratio: 2 / 3;
		border: var(--border);
		border-radius: 2px;
		overflow: hidden;
		background: var(--bg-warm);
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.text {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		min-width: 0;
	}
	.title {
		font-family: var(--f-serif);
		font-size: 1.15rem;
		line-height: 1.25;
		color: var(--ink);
		text-decoration: none;
		overflow-wrap: anywhere;
		transition: color 0.18s var(--ease-out);
	}
	.title:hover {
		color: var(--clay-deep);
	}
	.author {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		color: var(--muted);
	}
	.meta {
		font-size: 0.72rem;
		color: var(--faint);
		white-space: nowrap;
	}
	.remove {
		font-family: var(--f-grotesk);
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--muted);
		background: none;
		border: none;
		border-bottom: 1px solid transparent;
		padding: 0;
		cursor: pointer;
		transition: color 0.18s var(--ease-out);
	}
	.remove:hover {
		color: #b3402a;
		border-bottom-color: #b3402a;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.4rem;
		color: var(--muted);
		margin: 2rem 0 0.4rem;
	}
	.hint {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--faint);
		margin: 0;
	}

	@media (max-width: 560px) {
		.queue {
			padding: var(--page-pt) var(--page-h) 3rem;
		}
		.row {
			grid-template-columns: 2.9rem 1fr auto;
			grid-template-rows: auto auto;
		}
		.num {
			display: none;
		}
		.thumb {
			grid-row: 1 / span 2;
		}
		.meta {
			grid-column: 2;
			grid-row: 2;
			justify-self: start;
		}
		.remove {
			grid-row: 1 / span 2;
		}
	}
</style>
