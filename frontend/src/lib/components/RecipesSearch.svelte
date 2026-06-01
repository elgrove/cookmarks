<script module lang="ts">
	import type { KeywordSummary, RecipeSearchResults, SearchCriteria, SortKey } from '$lib/api/recipes';

	export type SearchStatus = 'resting' | 'loading' | 'results' | 'empty' | 'error';

	export type RecipesSearchProps = {
		status?: SearchStatus;
		results?: RecipeSearchResults;
		keywords?: KeywordSummary[];
		books?: { id: string; title: string }[];
		authors?: string[];
		criteria?: SearchCriteria;
		onSearch?: (criteria: SearchCriteria) => void;
	};
</script>

<script lang="ts">
	import RecipeRow from './RecipeRow.svelte';

	let {
		status = 'resting',
		results = { total: 0, items: [] },
		keywords = [],
		books = [],
		authors = [],
		criteria = {},
		onSearch
	}: RecipesSearchProps = $props();

	const sortOptions: { key: SortKey; label: string }[] = [
		{ key: 'name', label: 'Name A–Z' },
		{ key: 'recent', label: 'Recently added' }
	];

	// The component owns the live criteria so it stays interactive in isolation
	// (the route feeds results/status back in; this drives the controls' state).
	// Seeded once from the incoming criteria; the route owns it thereafter.
	// svelte-ignore state_referenced_locally
	const seed: SearchCriteria = criteria;
	const limit = seed.limit ?? 30;
	let query = $state(seed.q ?? '');
	let selected = $state<string[]>(seed.keywords ?? []);
	let bookId = $state(seed.bookId ?? '');
	let author = $state(seed.author ?? '');
	let sort = $state<SortKey>(seed.sort ?? 'name');
	let offset = $state(seed.offset ?? 0);

	let active = $derived(
		Boolean(query.trim() || selected.length || bookId || author)
	);

	let rangeStart = $derived(results.items.length ? offset + 1 : 0);
	let rangeEnd = $derived(offset + results.items.length);
	let canPrev = $derived(offset > 0);
	let canNext = $derived(offset + limit < results.total);

	function emit(resetOffset = true): void {
		if (resetOffset) offset = 0;
		onSearch?.({
			q: query,
			keywords: selected,
			bookId: bookId || undefined,
			author: author || undefined,
			sort,
			limit,
			offset
		});
	}

	let debounce: ReturnType<typeof setTimeout>;
	function onQueryInput(value: string): void {
		query = value;
		clearTimeout(debounce);
		debounce = setTimeout(() => emit(), 250);
	}

	function toggleKeyword(name: string): void {
		selected = selected.includes(name)
			? selected.filter((k) => k !== name)
			: [...selected, name];
		emit();
	}

	function prev(): void {
		offset = Math.max(0, offset - limit);
		emit(false);
	}
	function next(): void {
		offset = offset + limit;
		emit(false);
	}
</script>

<section
	class="search"
	data-verify-unit="recipes-search"
	data-verify-status={status}
	data-verify-resting={status === 'resting' ? 'true' : 'false'}
	data-verify-active={active ? 'true' : 'false'}
	data-verify-total={results.total}
	data-verify-shown={results.items.length}
	data-verify-query={query}
	data-verify-keywords={selected.join('|')}
	data-verify-book={bookId}
	data-verify-author={author}
	data-verify-sort={sort}
>
	<header class="head">
		<p class="label">Search</p>
		<h1 class="display">Recipes</h1>
	</header>

	<div class="controls">
		<div class="searchbox">
			<input
				type="search"
				class="search-input"
				placeholder="Search by name, ingredient, keyword, book or author…"
				aria-label="Search recipes"
				value={query}
				oninput={(e) => onQueryInput(e.currentTarget.value)}
			/>
			{#if query}
				<button
					class="clear"
					aria-label="Clear search"
					onclick={() => {
						query = '';
						emit();
					}}>×</button
				>
			{/if}
		</div>

		<label class="sort">
			<span class="label">Sort</span>
			<select
				class="select"
				aria-label="Sort recipes"
				value={sort}
				oninput={(e) => {
					sort = e.currentTarget.value as SortKey;
					emit();
				}}
			>
				{#each sortOptions as opt (opt.key)}
					<option value={opt.key}>{opt.label}</option>
				{/each}
			</select>
		</label>
	</div>

	<div class="filters">
		<label class="filter">
			<span class="label">Book</span>
			<select
				class="select"
				aria-label="Filter by book"
				value={bookId}
				oninput={(e) => {
					bookId = e.currentTarget.value;
					emit();
				}}
			>
				<option value="">All books</option>
				{#each books as b (b.id)}
					<option value={b.id}>{b.title}</option>
				{/each}
			</select>
		</label>

		<label class="filter">
			<span class="label">Author</span>
			<select
				class="select"
				aria-label="Filter by author"
				value={author}
				oninput={(e) => {
					author = e.currentTarget.value;
					emit();
				}}
			>
				<option value="">All authors</option>
				{#each authors as a (a)}
					<option value={a}>{a}</option>
				{/each}
			</select>
		</label>
	</div>

	{#if keywords.length}
		<ul class="chips" aria-label="Filter by keyword">
			{#each keywords as kw (kw.name)}
				<li>
					<button
						class="chip"
						class:on={selected.includes(kw.name)}
						aria-pressed={selected.includes(kw.name)}
						onclick={() => toggleKeyword(kw.name)}
					>
						{kw.name}<span class="chip-count">{kw.recipe_count}</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}

	<div class="results">
		{#if status === 'loading'}
			<ul class="skeleton" aria-hidden="true">
				{#each Array(6) as _, i (i)}
					<li class="skel-row"></li>
				{/each}
			</ul>
		{:else if status === 'error'}
			<p class="state">Couldn’t run the search. Try again.</p>
		{:else if status === 'resting'}
			<p class="state resting">
				Search your archive — by name, ingredient, keyword, book or author. Pick a keyword or book to
				browse.
			</p>
		{:else if results.items.length === 0}
			<p class="state">No recipes match your search.</p>
		{:else}
			<p class="count mono">{rangeStart}–{rangeEnd} of {results.total}</p>
			<ul class="rows">
				{#each results.items as r (r.id)}
					<RecipeRow
						id={r.id}
						name={r.name}
						bookId={r.book_id}
						bookTitle={r.book_title}
						bookAuthor={r.book_author}
						keywords={r.keywords}
					/>
				{/each}
			</ul>
			{#if canPrev || canNext}
				<nav class="pager" aria-label="Pagination">
					<button class="page-btn" disabled={!canPrev} onclick={prev}>← Previous</button>
					<button class="page-btn" disabled={!canNext} onclick={next}>Next →</button>
				</nav>
			{/if}
		{/if}
	</div>
</section>

<style>
	.search {
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

	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem 1.5rem;
		margin-bottom: 1.1rem;
	}

	.searchbox {
		position: relative;
		display: flex;
		align-items: center;
		flex: 1 1 22rem;
		min-width: 0;
	}

	.search-input {
		width: 100%;
		font-family: var(--f-grotesk);
		font-size: 1.05rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.6rem 1.5rem 0.6rem 0;
		transition: border-color 0.18s var(--ease-out);
	}

	.search-input::placeholder {
		color: var(--faint);
	}

	/* Hide the native clear affordance — we render our own. */
	.search-input::-webkit-search-cancel-button {
		-webkit-appearance: none;
		appearance: none;
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

	.sort,
	.filter {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
	}

	.select {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background-color: var(--bg);
		border: var(--border);
		border-radius: 3px;
		padding: 0.4rem 1.9rem 0.4rem 0.7rem;
		cursor: pointer;
		max-width: 16rem;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='7' viewBox='0 0 10 7'%3E%3Cpath d='M1 1.5l4 4 4-4' fill='none' stroke='%2386847b' stroke-width='1.5'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.65rem center;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 1.5rem;
		margin-bottom: 1.25rem;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		list-style: none;
		margin: 0 0 2.25rem;
		padding: 1.25rem 0 0;
		border-top: var(--border);
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.02em;
		color: var(--muted);
		background: var(--bg-warm);
		border: var(--border);
		border-radius: 999px;
		padding: 0.25rem 0.7rem;
		cursor: pointer;
		transition:
			border-color 0.16s var(--ease-out),
			color 0.16s var(--ease-out),
			background 0.16s var(--ease-out);
	}

	.chip:hover {
		border-color: var(--clay);
		color: var(--ink);
	}

	.chip.on {
		background: var(--clay);
		border-color: var(--clay);
		color: var(--bg);
	}

	.chip-count {
		font-size: 0.64rem;
		color: var(--faint);
	}

	.chip.on .chip-count {
		color: var(--bg);
		opacity: 0.8;
	}

	.count {
		color: var(--muted);
		margin: 0 0 0.5rem;
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: var(--border);
	}

	.state {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		line-height: 1.5;
		color: var(--muted);
		max-width: 32rem;
		padding: 2.5rem 0;
		margin: 0;
	}

	.skeleton {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: var(--border);
	}

	.skel-row {
		height: 1.2rem;
		margin: 1.4rem 0;
		background: var(--bg-warm);
		border-radius: 3px;
		animation: pulse 1.4s var(--ease-out) infinite;
	}

	.pager {
		display: flex;
		gap: 1rem;
		margin-top: 2rem;
	}

	.page-btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		color: var(--ink);
		background: none;
		border: var(--border);
		border-radius: 3px;
		padding: 0.45rem 0.9rem;
		cursor: pointer;
		transition: border-color 0.16s var(--ease-out);
	}

	.page-btn:hover:not(:disabled) {
		border-color: var(--clay);
	}

	.page-btn:disabled {
		color: var(--faint);
		cursor: default;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.45;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.skel-row {
			animation: none;
		}
	}

	@media (max-width: 760px) {
		.search {
			padding: 2rem var(--page-h) 3rem;
		}
	}
</style>
