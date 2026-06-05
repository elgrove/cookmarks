<script module lang="ts">
	export type LibraryBook = {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		hasCover: boolean;
	};

	type SortKey = 'recent' | 'title' | 'author' | 'recipes';
</script>

<script lang="ts">
	import BookCard from './BookCard.svelte';

	let { books }: { books: LibraryBook[] } = $props();

	let search = $state('');
	let sort = $state<SortKey>('recent');
	let extractedOnly = $state(false);

	const sortOptions: { key: SortKey; label: string }[] = [
		{ key: 'recent', label: 'Recently added' },
		{ key: 'title', label: 'Title A–Z' },
		{ key: 'author', label: 'Author' },
		{ key: 'recipes', label: 'Most recipes' }
	];

	let query = $derived(search.trim().toLowerCase());

	let visible = $derived.by(() => {
		let list = books;
		if (query) {
			list = list.filter(
				(b) => b.title.toLowerCase().includes(query) || b.author.toLowerCase().includes(query)
			);
		}
		if (extractedOnly) {
			list = list.filter((b) => b.recipeCount > 0);
		}
		const sorted = [...list];
		switch (sort) {
			case 'title':
				sorted.sort((a, b) => a.title.localeCompare(b.title));
				break;
			case 'author':
				sorted.sort((a, b) => a.author.localeCompare(b.author) || a.title.localeCompare(b.title));
				break;
			case 'recipes':
				sorted.sort((a, b) => b.recipeCount - a.recipeCount);
				break;
			// 'recent' keeps the incoming order (created_at desc)
		}
		return sorted;
	});

	let pendingCount = $derived(visible.filter((b) => b.recipeCount === 0).length);
	let filtered = $derived(Boolean(query) || extractedOnly);
	let countLabel = $derived(filtered ? `${visible.length} of ${books.length}` : `${books.length}`);
</script>

<section
	class="library"
	data-verify-unit="books-library"
	data-verify-count={visible.length}
	data-verify-total={books.length}
	data-verify-empty={visible.length === 0 ? 'true' : 'false'}
	data-verify-pending={pendingCount}
	data-verify-sort={sort}
	data-verify-query={query}
	data-verify-extracted-only={extractedOnly ? 'true' : 'false'}
	data-verify-first={visible[0]?.title ?? ''}
>
	<header class="head">
		<h1 class="display">Books</h1>
	</header>

	<div class="controls">
		<div class="search">
			<input
				type="search"
				class="search-input"
				placeholder="Search by title or author…"
				aria-label="Search books"
				value={search}
				oninput={(e) => (search = e.currentTarget.value)}
			/>
			{#if search}
				<button class="clear" aria-label="Clear search" onclick={() => (search = '')}>×</button>
			{/if}
		</div>

		<label class="sort">
			<span class="label">Sort</span>
			<select
				class="sort-select"
				aria-label="Sort books"
				value={sort}
				oninput={(e) => (sort = e.currentTarget.value as SortKey)}
			>
				{#each sortOptions as opt (opt.key)}
					<option value={opt.key}>{opt.label}</option>
				{/each}
			</select>
		</label>

		<label class="extracted">
			<input
				type="checkbox"
				class="extracted-checkbox"
				aria-label="Show only books with extracted recipes"
				checked={extractedOnly}
				onchange={(e) => (extractedOnly = e.currentTarget.checked)}
			/>
			<span class="label">Extracted only</span>
		</label>

		<p class="count mono">{countLabel} {books.length === 1 ? 'book' : 'books'}</p>
	</div>

	{#if visible.length === 0}
		<p class="empty">
			{#if books.length === 0}No books yet.{:else if query}No books match “{search.trim()}”.{:else}No extracted books yet.{/if}
		</p>
	{:else}
		<ul class="grid">
			{#each visible as book, i (book.id)}
				<li class="cell" style={`animation-delay: ${Math.min(i * 30, 600)}ms`}>
					<BookCard
						id={book.id}
						title={book.title}
						author={book.author}
						recipeCount={book.recipeCount}
						hasCover={book.hasCover}
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
		margin-bottom: 1.75rem;
	}

	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3.2rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin: 0.2rem 0 0;
	}

	/* Controls bar */
	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem 1.5rem;
		margin-bottom: 2.5rem;
		padding-bottom: 1.25rem;
		border-bottom: var(--border);
	}

	.search {
		position: relative;
		display: flex;
		align-items: center;
		flex: 1 1 18rem;
		min-width: 0;
	}

	.search-input {
		width: 100%;
		font-family: var(--f-grotesk);
		font-size: 0.95rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.5rem 1.5rem 0.5rem 0;
		transition: border-color 0.18s var(--ease-out);
	}

	.search-input::placeholder {
		color: var(--faint);
	}

	.search-input:focus {
		border-bottom-color: var(--clay);
	}

	.clear {
		position: absolute;
		right: 0;
		display: flex;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--muted);
		font-size: 1.2rem;
		line-height: 1;
		padding: 0.15rem 0.25rem;
	}

	.clear:hover {
		color: var(--clay-deep);
	}

	.sort {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
	}

	.sort-select {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background-color: var(--bg);
		border: var(--border);
		border-radius: 3px;
		padding: 0.4rem 1.9rem 0.4rem 0.7rem;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='7' viewBox='0 0 10 7'%3E%3Cpath d='M1 1.5l4 4 4-4' fill='none' stroke='%2386847b' stroke-width='1.5'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.65rem center;
	}

	.extracted {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
		user-select: none;
	}

	.extracted-checkbox {
		appearance: none;
		width: 1rem;
		height: 1rem;
		margin: 0;
		border: 1px solid var(--line-strong);
		border-radius: 3px;
		background-color: var(--bg);
		cursor: pointer;
		transition:
			border-color 0.18s var(--ease-out),
			background-color 0.18s var(--ease-out);
	}

	.extracted-checkbox:checked {
		border-color: var(--clay);
		background-color: var(--clay);
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='8' viewBox='0 0 10 8'%3E%3Cpath d='M1 4l3 3 5-6' fill='none' stroke='%23faf9f5' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: center;
	}

	.extracted-checkbox:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: 2px;
	}

	.count {
		margin: 0 0 0 auto;
		color: var(--muted);
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
		padding: 2rem 0;
		margin: 0;
	}

	@media (max-width: 1280px) {
		.grid {
			grid-template-columns: repeat(3, 1fr);
		}
	}

	@media (max-width: 760px) {
		.library {
			padding: 2rem var(--page-h) 3rem;
		}
		.controls {
			gap: 0.75rem 1rem;
		}
		/* Hidden on mobile: with the filter checkbox added the count wraps to its own
		   line, wasting vertical space; the total is non-essential at this width. */
		.count {
			display: none;
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
