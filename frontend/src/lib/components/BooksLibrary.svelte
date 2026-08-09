<script module lang="ts">
	export type LibraryBook = {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		progress?: number | null;
		hasCover: boolean;
		keywords?: string[];
		/** 1-based position on the caller's reading queue; absent when not queued. */
		queuePosition?: number | null;
	};

	type SortKey = 'recent' | 'title' | 'author' | 'recipes' | 'queue';
</script>

<script lang="ts">
	import BookCard from './BookCard.svelte';

	let { books }: { books: LibraryBook[] } = $props();

	let search = $state('');
	let sort = $state<SortKey>('recent');
	let extractedOnly = $state(false);
	let selectedKeywords = $state<string[]>([]);

	const sortOptions: { key: SortKey; label: string }[] = [
		{ key: 'recent', label: 'Recently added' },
		{ key: 'title', label: 'Title A–Z' },
		{ key: 'author', label: 'Author' },
		{ key: 'recipes', label: 'Most recipes' },
		{ key: 'queue', label: 'Queue order' }
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
		if (selectedKeywords.length) {
			// AND across selected keywords: a book must carry every one, so each chip
			// narrows the grid further (mirrors the recipes-search facet behaviour).
			list = list.filter((b) => {
				const kws = b.keywords ?? [];
				return selectedKeywords.every((k) => kws.includes(k));
			});
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
			case 'queue':
				// Queued books lead in queue order; the rest follow in the incoming
				// (recently-added) order — Array.sort is stable, so they keep it.
				sorted.sort(
					(a, b) => (a.queuePosition ?? Infinity) - (b.queuePosition ?? Infinity)
				);
				break;
			// 'recent' keeps the incoming order (created_at desc)
		}
		return sorted;
	});

	let pendingCount = $derived(visible.filter((b) => b.recipeCount === 0).length);
	// How many visible books have been started — one progress rule each.
	let progressCount = $derived(
		visible.filter((b) => (b.progress ?? 0) > 0).length
	);
	let filtered = $derived(Boolean(query) || extractedOnly || selectedKeywords.length > 0);
	let countLabel = $derived(filtered ? `${visible.length} of ${books.length}` : `${books.length}`);

	// Book-keyword facets for the filter bar: each distinct book keyword and how many
	// books carry it, most-used first. Derived from the loaded library — no extra
	// request, since /api/books already carries each book's keywords.
	type KeywordFacet = { name: string; count: number };
	let keywordFacets = $derived.by<KeywordFacet[]>(() => {
		const counts = new Map<string, number>();
		for (const b of books) for (const k of b.keywords ?? []) counts.set(k, (counts.get(k) ?? 0) + 1);
		return [...counts.entries()]
			.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
			.map(([name, count]) => ({ name, count }));
	});

	// Selected keywords pinned first so they stay deselectable even when they'd fall
	// past the two-row clamp; the rest follow in most-used order.
	let chips = $derived.by<KeywordFacet[]>(() => {
		const pinned = keywordFacets.filter((f) => selectedKeywords.includes(f.name));
		const rest = keywordFacets.filter((f) => !selectedKeywords.includes(f.name));
		return [...pinned, ...rest];
	});

	function toggleKeyword(name: string): void {
		selectedKeywords = selectedKeywords.includes(name)
			? selectedKeywords.filter((k) => k !== name)
			: [...selectedKeywords, name];
	}

	function clearKeywords(): void {
		if (selectedKeywords.length) selectedKeywords = [];
	}

	// Clamp the chip bar to CHIP_LINES rows. Chips are variable-width, so we render
	// them all and measure: overflow rows are clipped and made inert (out of tab order
	// and the a11y tree). With no layout (jsdom/SSR) nothing measures and all show.
	const CHIP_LINES = 2;
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
			if (!hidden)
				visibleBottom = Math.max(visibleBottom, Math.round(li.getBoundingClientRect().bottom - top));
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
</script>

<section
	class="library"
	data-verify-unit="books-library"
	data-verify-count={visible.length}
	data-verify-total={books.length}
	data-verify-empty={visible.length === 0 ? 'true' : 'false'}
	data-verify-pending={pendingCount}
	data-verify-progress-count={progressCount}
	data-verify-sort={sort}
	data-verify-query={query}
	data-verify-extracted-only={extractedOnly ? 'true' : 'false'}
	data-verify-first={visible[0]?.title ?? ''}
	data-verify-kw-selected={selectedKeywords.join('|')}
	data-verify-kw-chips={chips.map((c) => c.name).join('|')}
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

	{#if chips.length}
		<section class="keywords">
			{#if selectedKeywords.length}
				<div class="keywords-head">
					<button class="clear-kw" onclick={clearKeywords}>
						Clear selection ({selectedKeywords.length})
					</button>
				</div>
			{/if}
			<ul
				class="chips"
				class:clamped={clampHeight != null}
				style:max-height={clampHeight != null ? `${clampHeight}px` : null}
				bind:this={chipsEl}
				aria-label="Filter books by keyword"
			>
				{#each chips as chip (chip.name)}
					<li>
						<button
							class="chip"
							class:on={selectedKeywords.includes(chip.name)}
							data-kw={chip.name}
							aria-pressed={selectedKeywords.includes(chip.name)}
							onclick={() => toggleKeyword(chip.name)}
						>
							{chip.name}<span class="chip-count">{chip.count}</span>
						</button>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

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
						progress={book.progress ?? null}
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
		padding: var(--page-pt) var(--page-h) 5rem;
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
		margin-bottom: 1.5rem;
	}

	/* Keyword filter bar — clamped to two rows; selected chips narrow the grid. The
	   region-dividing hairline sits below it (consistent with the recipes list, where
	   the divider separates the filter header from the content below — never below the
	   search box itself). */
	.keywords {
		margin: 0 0 2.5rem;
		padding-bottom: 1.5rem;
		border-bottom: var(--border);
	}

	.keywords-head {
		display: flex;
		justify-content: flex-end;
		margin-bottom: 0.9rem;
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

	/* Clamped to two rows by measurement; overflow chips stay in flow (so they remain
	   measurable) but are clipped and made inert. */
	.chips.clamped {
		overflow: hidden;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-family: var(--f-mono);
		font-size: 0.74rem;
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

	.chip:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: 1px;
	}

	.chip-count {
		font-size: 0.64rem;
		color: var(--faint);
	}

	.chip.on .chip-count {
		color: var(--bg);
		opacity: 0.8;
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
		gap: 1.5rem var(--col-gap);
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
			padding: var(--page-pt) var(--page-h) 3rem;
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
			gap: 1.25rem 1.5rem;
		}
	}

	/* Mobile: text-first rows instead of a cover grid — a continuous hairline
	   list (BookCard reshapes each cell into a row at the same breakpoint). */
	@media (max-width: 560px) {
		.grid {
			grid-template-columns: 1fr;
			gap: 0;
			border-top: var(--border);
		}
		.cell {
			border-bottom: var(--border);
		}
	}
</style>
