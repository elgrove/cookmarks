<script module lang="ts">
	export type LibraryBook = {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		hasCover: boolean;
	};
</script>

<script lang="ts">
	import BookCard from './BookCard.svelte';

	let { books }: { books: LibraryBook[] } = $props();

	let total = $derived(books.length);
	let pendingCount = $derived(books.filter((b) => b.recipeCount === 0).length);

	// Stable archival accession id from the book's position in the library.
	function accession(i: number): string {
		return `CM-${String(i + 1).padStart(3, '0')}`;
	}
</script>

<section
	class="library"
	data-verify-unit="books-library"
	data-verify-count={total}
	data-verify-empty={total === 0 ? 'true' : 'false'}
	data-verify-pending={pendingCount}
>
	<header class="head">
		<p class="label">The library</p>
		<h1 class="display">Books</h1>
		<p class="total mono">{total} {total === 1 ? 'book' : 'books'}</p>
	</header>

	{#if total === 0}
		<p class="empty">No books yet.</p>
	{:else}
		<ul class="grid">
			{#each books as book, i (book.id)}
				<li class="cell" style={`animation-delay: ${Math.min(i * 30, 600)}ms`}>
					<BookCard
						id={book.id}
						title={book.title}
						author={book.author}
						recipeCount={book.recipeCount}
						hasCover={book.hasCover}
						accession={accession(i)}
					/>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.library {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 3rem var(--page-h) 5rem;
	}

	.head {
		margin-bottom: 2.5rem;
	}

	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3.2rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin: 0.2rem 0 0.5rem;
	}

	.total {
		color: var(--muted);
		margin: 0;
	}

	.grid {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 2.5rem var(--col-gap);
	}

	.cell {
		animation: fadeUp 0.6s var(--ease-out) both;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		padding: 3rem 0;
		margin: 0;
	}

	@media (max-width: 1280px) {
		.grid {
			grid-template-columns: repeat(3, 1fr);
		}
	}

	@media (max-width: 760px) {
		.library {
			padding: 2rem 1.25rem 3rem;
		}
		.grid {
			grid-template-columns: repeat(2, 1fr);
			gap: 2rem 1.5rem;
		}
	}

	@media (max-width: 420px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>
