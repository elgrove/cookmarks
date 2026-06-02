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
	import { searchContextQuery } from '$lib/api/recipes';

	let {
		status = 'resting',
		results = { total: 0, items: [], facets: [] },
		keywords = [],
		books = [],
		authors = [],
		criteria = {},
		onSearch
	}: RecipesSearchProps = $props();

	const sortOptions: { key: SortKey; label: string }[] = [
		{ key: 'random', label: 'Random' },
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
	let sort = $state<SortKey>(seed.sort ?? 'random');
	let offset = $state(seed.offset ?? 0);

	// Random sort is seeded so a result set keeps its order across pagination; a
	// fresh seed is minted each time a *new* search starts (not on prev/next).
	let randomSeed = seed.seed ?? 0;

	let active = $derived(
		Boolean(query.trim() || selected.length || bookId || author)
	);

	// Carried into each result's link so the recipe page's prev/next follow this
	// exact search (filters + sort + seed).
	let contextQuery = $derived(
		searchContextQuery({
			q: query,
			keywords: selected,
			bookId: bookId || undefined,
			author: author || undefined,
			sort,
			seed: sort === 'random' ? randomSeed : undefined
		})
	);

	// The chips shown: selected keywords pinned first (so they stay deselectable
	// even when they drop out of the facets), then the co-occurrence facets. A
	// pinned chip has no count — it's already chosen, every result carries it.
	const CHIP_CAP = 50;
	type DisplayChip = { name: string; count: number | null };
	let chips = $derived.by<DisplayChip[]>(() => {
		const pinned = selected
			.filter((name) => !keywords.some((k) => k.name === name))
			.map((name) => ({ name, count: null }));
		const room = Math.max(0, CHIP_CAP - pinned.length);
		const facets = keywords
			.slice(0, room)
			.map((k) => ({ name: k.name, count: k.recipe_count }));
		return [...pinned, ...facets];
	});

	// Clamp the chips to at most CHIP_LINES rows. Chips are variable-width, so we
	// render them all and measure: overflow rows are clipped away and made inert
	// (out of tab order / the a11y tree). With no layout (jsdom/SSR) nothing is
	// measured and everything shows.
	const CHIP_LINES = 4;
	let chipsEl = $state<HTMLUListElement>();
	let clampHeight = $state<number | null>(null);

	function clampChips(): void {
		const ul = chipsEl;
		if (!ul) return;
		const lis = [...ul.querySelectorAll<HTMLLIElement>(':scope > li')];
		if (!lis.length) {
			clampHeight = null;
			return;
		}
		const top = ul.getBoundingClientRect().top;
		const rowTops: number[] = [];
		const liTops = lis.map((li) => {
			const t = Math.round(li.getBoundingClientRect().top - top);
			if (!rowTops.some((r) => Math.abs(r - t) < 2)) rowTops.push(t);
			return t;
		});
		rowTops.sort((a, b) => a - b);
		let firstHidden = lis.length;
		if (rowTops.length > CHIP_LINES) {
			const cut = rowTops[CHIP_LINES];
			const idx = liTops.findIndex((t) => t >= cut - 1);
			if (idx !== -1) firstHidden = idx;
		}
		let visibleBottom = 0;
		lis.forEach((li, i) => {
			const hidden = i >= firstHidden;
			li.inert = hidden;
			if (!hidden) {
				visibleBottom = Math.max(visibleBottom, Math.round(li.getBoundingClientRect().bottom - top));
			}
		});
		clampHeight = firstHidden < lis.length ? visibleBottom : null;
	}

	$effect(() => {
		chips; // re-clamp whenever the chip set changes
		clampChips();
	});

	$effect(() => {
		const ul = chipsEl;
		if (!ul || typeof ResizeObserver === 'undefined') return;
		let lastWidth = -1;
		const ro = new ResizeObserver((entries) => {
			const width = entries[0].contentRect.width;
			if (Math.abs(width - lastWidth) < 0.5) return; // ignore our own height changes
			lastWidth = width;
			clampChips();
		});
		ro.observe(ul);
		return () => ro.disconnect();
	});

	$effect(() => {
		// Chips reflow once the mono font loads — re-measure then.
		if (typeof document !== 'undefined' && document.fonts) {
			void document.fonts.ready.then(() => clampChips());
		}
	});

	let rangeStart = $derived(results.items.length ? offset + 1 : 0);
	let rangeEnd = $derived(offset + results.items.length);
	let canPrev = $derived(offset > 0);
	let canNext = $derived(offset + limit < results.total);

	function emit(resetOffset = true): void {
		if (resetOffset) {
			offset = 0;
			// New search → reshuffle. Pagination (resetOffset=false) keeps the seed
			// so the user pages through one stable random ordering.
			if (sort === 'random') randomSeed = Math.floor(Math.random() * 2_000_000_000) + 1;
		}
		onSearch?.({
			q: query,
			keywords: selected,
			bookId: bookId || undefined,
			author: author || undefined,
			sort,
			seed: sort === 'random' ? randomSeed : undefined,
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

	function clearKeywords(): void {
		if (!selected.length) return;
		selected = [];
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
	data-verify-chips={chips.map((c) => c.name).join('|')}
	data-verify-book={bookId}
	data-verify-author={author}
	data-verify-sort={sort}
>
	<header class="head">
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

	{#if chips.length}
		<section class="keywords">
			<div class="keywords-head">
				<p class="label kw-label">Keywords</p>
				{#if selected.length}
					<button class="clear-kw" onclick={clearKeywords}>
						Clear selection ({selected.length})
					</button>
				{/if}
			</div>
			<ul
				class="chips"
				class:clamped={clampHeight != null}
				style:max-height={clampHeight != null ? `${clampHeight}px` : null}
				bind:this={chipsEl}
				aria-label="Filter by keyword"
			>
				{#each chips as chip (chip.name)}
					<li>
						<button
							class="chip"
							class:on={selected.includes(chip.name)}
							aria-pressed={selected.includes(chip.name)}
							onclick={() => toggleKeyword(chip.name)}
						>
							{chip.name}{#if chip.count !== null}<span class="chip-count">{chip.count}</span
								>{/if}
						</button>
					</li>
				{/each}
			</ul>
		</section>
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
			<!-- Empty until a query: the controls above are the whole prompt. -->
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
						{contextQuery}
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

	.keywords {
		margin: 0 0 2.5rem;
		padding: 1.5rem 0 0;
		border-top: 2px solid var(--line-strong);
	}

	.keywords-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	/* A touch larger and darker than the standard control label — the keyword
	   facets are the primary way to explore the archive, so they lead. */
	.kw-label {
		font-size: 0.8rem;
		letter-spacing: 0.1em;
		color: var(--ink);
	}

	.clear-kw {
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.02em;
		color: var(--muted);
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		text-decoration: underline;
		text-underline-offset: 3px;
		transition: color 0.16s var(--ease-out);
	}

	.clear-kw:hover {
		color: var(--clay-deep);
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/* Clamped to a fixed number of rows by measurement; overflow chips stay in
	   flow (so they remain measurable) but are clipped and made inert. */
	.chips.clamped {
		overflow: hidden;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-family: var(--f-mono);
		font-size: 0.76rem;
		letter-spacing: 0.02em;
		color: var(--muted);
		background: var(--bg-warm);
		border: var(--border);
		border-radius: 999px;
		padding: 0.3rem 0.78rem;
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
