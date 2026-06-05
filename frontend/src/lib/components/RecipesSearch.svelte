<script module lang="ts">
	import type { KeywordSummary, RecipeSearchResults, SearchCriteria, SortKey } from '$lib/api/recipes';

	export type SearchStatus = 'resting' | 'loading' | 'results' | 'empty' | 'error';
	// Which search the box last ran. Keyword = literal match shaped by the filters;
	// semantic = ranked by meaning, with the filters set aside.
	export type SearchMode = 'keyword' | 'semantic';

	export type RecipesSearchProps = {
		status?: SearchStatus;
		mode?: SearchMode;
		results?: RecipeSearchResults;
		// False when semantic search can't run (no embedding-capable provider): the
		// results area says so instead of implying nothing matched.
		semanticAvailable?: boolean;
		keywords?: KeywordSummary[];
		books?: { id: string; title: string }[];
		authors?: string[];
		criteria?: SearchCriteria;
		onSearch?: (criteria: SearchCriteria) => void;
		onSemanticSearch?: (query: string) => void;
	};
</script>

<script lang="ts">
	import RecipeRow from './RecipeRow.svelte';
	import { searchContextQuery } from '$lib/api/recipes';

	let {
		status = 'resting',
		mode = 'keyword',
		results = { total: 0, items: [], facets: [] },
		semanticAvailable = true,
		keywords = [],
		books = [],
		authors = [],
		criteria = {},
		onSearch,
		onSemanticSearch
	}: RecipesSearchProps = $props();

	const sortOptions: { key: SortKey; label: string }[] = [
		{ key: 'random', label: 'Random' },
		{ key: 'name', label: 'Name A–Z' },
		{ key: 'recent', label: 'Recently added' },
		{ key: 'book', label: 'Book order' }
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
	// The active search mode is live in the box (a button press flips it); seeded
	// from the prop so a restored ?mode=idea URL opens in semantic mode.
	// svelte-ignore state_referenced_locally
	let searchMode = $state<SearchMode>(mode);

	// Random sort is seeded so a result set keeps its order across pagination; a
	// fresh seed is minted each time a *new* search starts (not on prev/next).
	let randomSeed = seed.seed ?? 0;

	let active = $derived(Boolean(query.trim() || selected.length || bookId || author));
	let isSemantic = $derived(searchMode === 'semantic');

	// Mobile collapses the book/author/sort/keyword controls behind a "Filters"
	// disclosure to save vertical space; the count keeps applied filters visible
	// while collapsed. Desktop shows everything and ignores `filtersOpen` (CSS).
	let filtersOpen = $state(false);
	let activeFilterCount = $derived((bookId ? 1 : 0) + (author ? 1 : 0) + selected.length);

	// A concise placeholder on narrow screens — the full prompt overflows the box
	// once the magnifier + AI buttons claim their width.
	let narrow = $state(false);
	$effect(() => {
		if (typeof window === 'undefined' || !window.matchMedia) return;
		const mq = window.matchMedia('(max-width: 560px)');
		const sync = () => (narrow = mq.matches);
		sync();
		mq.addEventListener('change', sync);
		return () => mq.removeEventListener('change', sync);
	});
	let placeholder = $derived(
		narrow ? 'Search or describe a dish…' : 'Search recipes, or describe a dish…'
	);

	// Carried into each result's link so the recipe page's prev/next follow this
	// exact search (keyword filters + sort + seed). Semantic results have no such
	// ordering wired, so they open in the recipe's own book context.
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
		filtersOpen; // ...and when the mobile filter panel reveals the chips
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

	// Run the keyword search. Any keyword-side interaction (typing, a chip, a
	// filter, the magnifier) routes through here and switches the box to keyword
	// mode, so the filters always describe what's on screen.
	function emitKeyword(resetOffset = true): void {
		searchMode = 'keyword';
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

	// Run the semantic search on the current text — the only path into semantic
	// mode (the lightbulb / Enter-on-the-idea side). Disabled while the box is empty.
	function runSemantic(): void {
		if (!query.trim()) return;
		// Cancel any pending debounced keyword search from earlier typing.
		clearTimeout(debounce);
		searchMode = 'semantic';
		onSemanticSearch?.(query.trim());
	}

	let debounce: ReturnType<typeof setTimeout>;
	function onQueryInput(value: string): void {
		query = value;
		clearTimeout(debounce);
		// Typing is the live keyword search; semantic is always an explicit press.
		debounce = setTimeout(() => emitKeyword(), 250);
	}

	function onSearchKeydown(e: KeyboardEvent): void {
		if (e.key === 'Enter') {
			e.preventDefault();
			clearTimeout(debounce);
			emitKeyword();
		}
	}

	function clearSearch(): void {
		query = '';
		clearTimeout(debounce);
		emitKeyword();
	}

	function toggleKeyword(name: string): void {
		selected = selected.includes(name)
			? selected.filter((k) => k !== name)
			: [...selected, name];
		emitKeyword();
	}

	function clearKeywords(): void {
		if (!selected.length) return;
		selected = [];
		emitKeyword();
	}

	function prev(): void {
		offset = Math.max(0, offset - limit);
		emitKeyword(false);
	}
	function next(): void {
		offset = offset + limit;
		emitKeyword(false);
	}
</script>

<section
	class="search"
	data-verify-unit="recipes-search"
	data-verify-status={status}
	data-verify-mode={searchMode}
	data-verify-resting={status === 'resting' ? 'true' : 'false'}
	data-verify-active={active ? 'true' : 'false'}
	data-verify-available={semanticAvailable ? 'true' : 'false'}
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

	<div class="searchrow">
		<input
			type="search"
			class="search-input"
			{placeholder}
			aria-label="Search recipes"
			value={query}
			oninput={(e) => onQueryInput(e.currentTarget.value)}
			onkeydown={onSearchKeydown}
		/>
		{#if query}
			<button class="clear" aria-label="Clear search" onclick={clearSearch}>×</button>
		{/if}
		<button
			class="iconbtn ib-search"
			type="button"
			aria-label="Search"
			title="Search"
			onclick={() => emitKeyword()}
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7.5" /><line x1="16.8" y1="16.8" x2="21" y2="21" /></svg>
		</button>
		<button
			class="iconbtn ib-ai"
			type="button"
			aria-label="AI search"
			title="AI search — describe a dish"
			onclick={runSemantic}
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3Z" /></svg>
		</button>
	</div>

	<button
		class="filters-toggle"
		class:dimmed={isSemantic}
		type="button"
		aria-expanded={filtersOpen}
		onclick={() => (filtersOpen = !filtersOpen)}
	>
		<span class="ft-label"
			>Filters{#if activeFilterCount}<span class="ft-count">{activeFilterCount}</span>{/if}</span
		>
		<svg
			class="ft-chev"
			class:open={filtersOpen}
			viewBox="0 0 10 7"
			aria-hidden="true"
			fill="none"
			stroke="currentColor"
			stroke-width="1.5"><path d="M1 1.5l4 4 4-4" /></svg
		>
	</button>

	<div class="filter-panel" class:open={filtersOpen}>
		<div class="filters" class:dimmed={isSemantic}>
			<label class="filter">
				<span class="label">Book</span>
			<select
				class="select"
				aria-label="Filter by book"
				value={bookId}
				oninput={(e) => {
					bookId = e.currentTarget.value;
					emitKeyword();
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
					emitKeyword();
				}}
			>
				<option value="">All authors</option>
				{#each authors as a (a)}
					<option value={a}>{a}</option>
				{/each}
			</select>
		</label>

		<label class="filter">
			<span class="label">Sort</span>
			<select
				class="select"
				aria-label="Sort recipes"
				value={sort}
				oninput={(e) => {
					sort = e.currentTarget.value as SortKey;
					emitKeyword();
				}}
			>
				{#each sortOptions as opt (opt.key)}
					<option value={opt.key}>{opt.label}</option>
				{/each}
			</select>
		</label>
	</div>

	{#if chips.length}
		<section class="keywords" class:dimmed={isSemantic}>
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
	</div>

	<div class="results">
		{#if status === 'loading'}
			<ul class="skeleton" aria-hidden="true">
				{#each Array(6) as _, i (i)}
					<li class="skel-row"></li>
				{/each}
			</ul>
		{:else if status === 'error'}
			<p class="state">Couldn’t run the search. Try again.</p>
		{:else if isSemantic && !semanticAvailable}
			<p class="state">Semantic search needs an AI provider configured.</p>
		{:else if status === 'resting'}
			<!-- Empty until a query: the controls above are the whole prompt. -->
		{:else if results.items.length === 0}
			<p class="state">
				{isSemantic ? 'No recipes match your description.' : 'No recipes match your search.'}
			</p>
		{:else}
			<p class="count mono">
				{#if isSemantic}
					{results.total} {results.total === 1 ? 'result' : 'results'} · most relevant first
				{:else}
					{rangeStart}–{rangeEnd} of {results.total}
				{/if}
			</p>
			<ul class="rows">
				{#each results.items as r (r.id)}
					<RecipeRow
						id={r.id}
						name={r.name}
						bookId={r.book_id}
						bookTitle={r.book_title}
						bookAuthor={r.book_author}
						keywords={r.keywords}
						contextQuery={isSemantic ? '' : contextQuery}
					/>
				{/each}
			</ul>
			{#if !isSemantic && (canPrev || canNext)}
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

	/* One box, two inline icon triggers — magnifier (keyword) + lightbulb (idea). */
	.searchrow {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		margin-bottom: 1.4rem;
	}

	.search-input {
		flex: 1 1 auto;
		min-width: 0;
		font-family: var(--f-grotesk);
		font-size: 1.05rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.6rem 0.25rem 0.6rem 0;
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
		outline: none;
		border-bottom-color: var(--clay);
	}

	.clear {
		flex: none;
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

	.iconbtn {
		flex: none;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.65rem;
		height: 2.65rem;
		border-radius: 3px;
		cursor: pointer;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out),
			opacity 0.18s var(--ease-out);
	}

	.iconbtn svg {
		display: block;
		width: 1.15rem;
		height: 1.15rem;
	}

	.ib-search {
		background: var(--ink);
		color: var(--bg);
		border: 1px solid var(--ink);
	}

	.ib-search:hover {
		opacity: 0.85;
	}

	.ib-ai {
		background: none;
		color: var(--clay-deep);
		border: 1px solid var(--clay);
	}

	.ib-ai:hover {
		background: var(--chip-clay);
	}

	/* In semantic mode the keyword filters don't shape the results — fade them back
	   so that reads, while leaving them live (touching one returns to keyword). */
	.dimmed {
		opacity: 0.45;
		transition: opacity 0.18s var(--ease-out);
	}

	/* Filters disclosure. Desktop: the toggle is hidden and the panel is
	   display:contents (invisible to layout — controls flow exactly as before).
	   Mobile (≤760): the toggle appears and the panel collapses behind it. */
	.filters-toggle {
		display: none;
	}

	.filter-panel {
		display: contents;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 1.5rem;
		margin-bottom: 1.25rem;
	}

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

		/* Tighter search row so the box keeps room beside the two icon triggers. */
		.search-input {
			font-size: 1rem;
		}
		.searchrow {
			gap: 0.4rem;
		}
		.iconbtn {
			width: 2.4rem;
			height: 2.4rem;
		}

		/* The filters disclosure. */
		.filters-toggle {
			display: inline-flex;
			align-items: center;
			gap: 0.55rem;
			margin-bottom: 1.25rem;
			padding: 0;
			background: none;
			border: none;
			cursor: pointer;
			font-family: var(--f-mono);
			font-size: 0.72rem;
			letter-spacing: 0.1em;
			text-transform: uppercase;
			color: var(--ink);
		}
		.ft-label {
			display: inline-flex;
			align-items: center;
			gap: 0.4rem;
		}
		.ft-count {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			min-width: 1.25rem;
			height: 1.25rem;
			padding: 0 0.3rem;
			border-radius: 999px;
			background: var(--clay);
			color: var(--bg);
			font-size: 0.66rem;
			letter-spacing: 0;
		}
		.ft-chev {
			width: 0.7rem;
			height: 0.7rem;
			color: var(--muted);
			transition: transform 0.18s var(--ease-out);
		}
		.ft-chev.open {
			transform: rotate(180deg);
		}

		.filter-panel {
			display: none;
		}
		.filter-panel.open {
			display: block;
		}

		/* Stacked, full-width controls when the panel is open. */
		.filters {
			flex-direction: column;
			align-items: stretch;
			gap: 0.85rem;
		}
		.filter {
			justify-content: space-between;
		}
		.select {
			flex: 1 1 auto;
			max-width: none;
			margin-left: 1rem;
		}
	}
</style>
