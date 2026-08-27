<script module lang="ts">
	export type BookDetailRecipe = {
		id: string;
		name: string;
		keywords: string[];
	};

	export type BookDetailData = {
		id: string;
		title: string;
		author: string;
		isbn: string | null;
		pubdate: string | null;
		description: string;
		recipeCount: number;
		hasCover: boolean;
		hasEpub: boolean;
		hasPdf: boolean;
		added: string | null;
		keywords: string[];
		recipes: BookDetailRecipe[];
		/** Whether the book sits on the caller's reading queue. */
		queued: boolean;
		/** How the book is being read and how far through it — measured in recipes
		 *  either way. Null until the book has been opened. */
		reading: { mode: 'book' | 'recipes'; fraction: number; finished: boolean } | null;
		/** Where reading the recipes picks up: the furthest reached, or the first. */
		resumeRecipe: { id: string; name: string } | null;
	};

	// Rotating chip tints (DESIGN §3.1), assigned deterministically per keyword.
	const CHIP_TINTS = ['', 'b', 'g'] as const;
	function chipClass(keyword: string): string {
		let h = 0;
		for (let i = 0; i < keyword.length; i++) h = (h + keyword.charCodeAt(i)) % CHIP_TINTS.length;
		return CHIP_TINTS[h];
	}

	const DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
	function formatDay(iso: string | null): string {
		if (!iso) return '';
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? '' : DAY.format(d);
	}
	function formatYear(iso: string | null): string {
		if (!iso) return '';
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? '' : String(d.getUTCFullYear());
	}
</script>

<script lang="ts">
	import { plainText } from '$lib/html';
	import { cleanTitle, titleSubtitle } from '$lib/title';
	import { keywordHref } from '$lib/api/recipes';
	import ExtractButton from '$lib/components/ExtractButton.svelte';
	import ReviewPrompt from '$lib/components/ReviewPrompt.svelte';
	import type { ReviewQuestion } from '$lib/api/task-runs';

	let {
		book,
		onExtract,
		review = null,
		onAnswer,
		onDelete,
		onMarkBookRead,
		onResetProgress,
		onToggleQueue
	}: {
		book: BookDetailData;
		onExtract?: () => Promise<void> | void;
		review?: ReviewQuestion | null;
		onAnswer?: (value: string) => Promise<void> | void;
		onDelete?: (opts: { exclude: boolean; fromLibrary: boolean }) => Promise<void> | void;
		onMarkBookRead?: () => Promise<void> | void;
		onResetProgress?: () => Promise<void> | void;
		onToggleQueue?: () => Promise<void> | void;
	} = $props();

	let coverFailed = $state(false);
	let expanded = $state(false);
	let deleteMode = $state<'view' | 'confirm'>('view');
	// How far the delete reaches: out of the app only (the next sync brings it back),
	// out of the app and off future syncs, or out of the Calibre library altogether.
	let deleteScope = $state<'app' | 'exclude' | 'library'>('app');
	let deleted = $state('');
	let resetMode = $state<'view' | 'confirm'>('view');
	// The last read-state action asked for, so the harness can verify the intent
	// this component emits (the owning route holds the state and re-renders).
	let seenAction = $state('');
	// Likewise for the queue toggle: 'queue' or 'unqueue', by the state it acted from.
	let queueAction = $state('');

	function confirmDelete() {
		deleted = deleteScope === 'app' ? 'plain' : deleteScope;
		onDelete?.({ exclude: deleteScope === 'exclude', fromLibrary: deleteScope === 'library' });
		deleteMode = 'view';
	}

	function confirmReset() {
		seenAction = 'reset';
		onResetProgress?.();
		resetMode = 'view';
	}
	let showCover = $derived(book.hasCover && !coverFailed);

	// Calibre titles pack a subtitle behind a colon; the first segment is the display title.
	let mainTitle = $derived(cleanTitle(book.title));
	let subtitle = $derived(titleSubtitle(book.title));

	let description = $derived(plainText(book.description));
	let year = $derived(formatYear(book.pubdate));
	let added = $derived(formatDay(book.added));
	let shown = $derived(book.recipes.length);
	let moreCount = $derived(Math.max(0, book.recipeCount - shown));
	// A book is read either way — its own pages, or its recipes one at a time — and both
	// share one position. Whichever mode it was last read in leads the actions, and only
	// that one is "continued".
	let mode = $derived(book.reading?.mode ?? null);
	let started = $derived(!!book.reading && !book.reading.finished && book.reading.fraction > 0);
	let readPct = $derived(book.reading ? Math.round(book.reading.fraction * 100) : null);
	let readable = $derived(book.hasEpub || book.hasPdf);
</script>

<article
	class="book"
	data-verify-unit="book-detail"
	data-verify-id={book.id}
	data-verify-recipe-count={book.recipeCount}
	data-verify-read-pct={readPct === null ? '' : readPct}
	data-verify-shown={shown}
	data-verify-has-cover={book.hasCover ? 'true' : 'false'}
	data-verify-has-epub={book.hasEpub ? 'true' : 'false'}
	data-verify-has-pdf={book.hasPdf ? 'true' : 'false'}
	data-verify-empty={book.recipeCount === 0 ? 'true' : 'false'}
	data-verify-keywords={book.keywords.length}
	data-verify-delete-mode={deleteMode}
	data-verify-delete-exclude={deleteScope === 'exclude' ? 'true' : 'false'}
	data-verify-delete-scope={deleteScope}
	data-verify-deleted={deleted}
	data-verify-seen-action={seenAction}
	data-verify-queued={book.queued ? 'true' : 'false'}
	data-verify-queue-action={queueAction}
	data-verify-reset-mode={resetMode}
	data-verify-resume-recipe={book.resumeRecipe?.id ?? ''}
	data-verify-reading-mode={mode ?? ''}
	data-verify-started={started ? 'true' : 'false'}
>
	<nav class="crumb" aria-label="Breadcrumb">
		<a href="/books">Books</a><span class="sep">›</span><a
			href={`/books?author=${encodeURIComponent(book.author)}`}>{book.author}</a
		><span class="sep">›</span><span class="here">{mainTitle}</span>
	</nav>

	{#if review}
		<div class="review-slot">
			<ReviewPrompt {review} {onAnswer} />
		</div>
	{/if}

	<div class="cols">
		<header class="masthead">
			<h1 class="display">{mainTitle}</h1>
			{#if subtitle}<p class="subtitle">{subtitle}</p>{/if}
			<p class="byline">by <b>{book.author}</b></p>
			{#if book.keywords.length}
				<ul class="book-tags" aria-label="Book keywords">
					{#each book.keywords as kw (kw)}
						<li><a class="chip {chipClass(kw)}" href={keywordHref(kw)}>{kw}</a></li>
					{/each}
				</ul>
			{/if}
		</header>

		<main class="reading">
			{#if description}
				<div class="lede" class:clamped={!expanded}>
					<p>{description}</p>
				</div>
				{#if description.length > 360}
					<button class="readmore" onclick={() => (expanded = !expanded)}>
						{expanded ? 'Read less' : 'Read more'}
					</button>
				{/if}
			{/if}

			<p class="label rlabel">Recipes</p>
			{#if book.recipeCount === 0}
				<p class="empty">No recipes extracted yet.</p>
			{:else}
				<ul class="index">
					{#each book.recipes as recipe (recipe.id)}
						<li data-verify-recipe={recipe.id}>
							<div class="entry">
								<div class="rtext">
									<div class="rname">
										<a href={`/recipes/${recipe.id}`}>{recipe.name}</a>
									</div>
									{#if recipe.keywords.length}
										<div class="chips">
											{#each recipe.keywords as kw (kw)}
												<a class="chip {chipClass(kw)}" href={keywordHref(kw)}>{kw}</a>
											{/each}
										</div>
									{/if}
								</div>
							</div>
						</li>
					{/each}
				</ul>
				{#if moreCount > 0}
					<p class="more">+ {moreCount} more</p>
				{/if}
			{/if}
		</main>

		<aside>
			<div class="plate">
				{#if showCover}
					<img
						class="cover"
						src={`/api/books/${book.id}/cover`}
						alt={`Cover of ${mainTitle}`}
						onerror={() => (coverFailed = true)}
					/>
				{:else}
					<span class="plate-title" aria-hidden="true">{mainTitle}</span>
				{/if}
				{#if book.recipeCount > 0}
					<span class="count-badge" aria-hidden="true">{book.recipeCount}</span>
				{/if}
			</div>

			<div class="actions">
				<!-- Two ways to read a book, one shared position; the mode last read leads. -->
				{#if readable}
					<a
						class="btn read-epub"
						class:primary={mode !== 'recipes'}
						class:ghost={mode === 'recipes'}
						style:order={mode === 'recipes' ? 2 : 1}
						href={`/books/${book.id}/read`}
					>
						{started ? 'Continue book' : 'Read book'}
						<span class="ar" aria-hidden="true">›</span>
					</a>
				{/if}
				{#if book.resumeRecipe}
					<a
						class="btn read-recipes"
						class:primary={mode === 'recipes' || !readable}
						class:ghost={mode !== 'recipes' && readable}
						style:order={mode === 'recipes' ? 1 : 2}
						href={`/recipes/${book.resumeRecipe.id}?context=book`}
						title={book.resumeRecipe.name}
					>
						{started ? 'Continue recipes' : 'Read recipes'}
						<span class="ar" aria-hidden="true">›</span>
					</a>
				{/if}
				{#if book.recipeCount > 0}
					<a class="btn ghost browse" href={`/recipes?book_id=${book.id}&sort=book`}>
						Browse recipes <span class="ar" aria-hidden="true">›</span>
					</a>
				{/if}
				{#if onToggleQueue}
					<button
						class="btn ghost queue-toggle"
						type="button"
						onclick={() => {
							queueAction = book.queued ? 'unqueue' : 'queue';
							onToggleQueue();
						}}
					>
						{book.queued ? 'Remove from queue' : 'Queue to read'}
						<span class="ar" aria-hidden="true">{book.queued ? '−' : '+'}</span>
					</button>
				{/if}
				{#if onMarkBookRead && !book.reading?.finished}
					<button
						class="btn ghost mark-read"
						type="button"
						onclick={() => {
							seenAction = 'book-read';
							onMarkBookRead();
						}}
					>
						Mark book read <span class="ar" aria-hidden="true">✓</span>
					</button>
				{/if}
				{#if onResetProgress && book.reading}
					{#if resetMode === 'confirm'}
						<div class="confirm">
							<p class="prompt">
								Forget which of this book's recipes you've read? The percentage returns to zero.
							</p>
							<button class="btn danger confirm-reset" type="button" onclick={confirmReset}>
								Reset progress
							</button>
							<button class="btn ghost" type="button" onclick={() => (resetMode = 'view')}>
								Cancel
							</button>
						</div>
					{:else}
						<button
							class="btn ghost reset-btn"
							type="button"
							onclick={() => (resetMode = 'confirm')}
						>
							Reset progress <span class="ar" aria-hidden="true">↺</span>
						</button>
					{/if}
				{/if}
				{#if onExtract}
					<ExtractButton
						recipeCount={book.recipeCount}
						{onExtract}
						unavailable={!book.hasEpub && !book.hasPdf}
					/>
				{/if}
				{#if onDelete}
					{#if deleteMode === 'confirm'}
						<div class="confirm">
							<p class="prompt">
								Delete this book?
								{#if book.recipeCount > 0}
									Its {book.recipeCount}
									{book.recipeCount === 1 ? 'recipe' : 'recipes'} are removed for good.
								{/if}
							</p>
							<fieldset class="scope">
								<legend>How far does it go?</legend>
								<label class="exclude">
									<input type="radio" value="app" bind:group={deleteScope} />
									From Cookmarks only — the next Calibre sync brings it back
								</label>
								<label class="exclude">
									<input type="radio" value="exclude" bind:group={deleteScope} />
									From Cookmarks, and exclude it from future Calibre syncs
								</label>
								<label class="exclude">
									<input type="radio" value="library" bind:group={deleteScope} />
									From the Calibre library too — the book file is deleted for good
								</label>
							</fieldset>
							<button class="btn danger confirm-delete" type="button" onclick={confirmDelete}>
								Delete book
							</button>
							<button
								class="btn ghost"
								type="button"
								onclick={() => {
									deleteMode = 'view';
									deleteScope = 'app';
								}}
							>
								Cancel
							</button>
						</div>
					{:else}
						<button
							class="btn ghost delete-btn"
							type="button"
							onclick={() => (deleteMode = 'confirm')}
						>
							Delete book
						</button>
					{/if}
				{/if}
			</div>

			<dl class="meta">
				<div><dt>Author</dt><dd>{book.author}</dd></div>
				{#if year}<div><dt>Published</dt><dd>{year}</dd></div>{/if}
				{#if book.isbn}<div><dt>ISBN</dt><dd>{book.isbn}</dd></div>{/if}
				<div><dt>Recipes</dt><dd>{book.recipeCount}</dd></div>
				{#if readPct !== null}
					<div>
						<dt>Read</dt>
						<dd class="read">
							<span class="pct">{readPct}%</span>
							{#if book.reading?.finished}<span class="of">finished</span>{/if}
						</dd>
					</div>
				{/if}
				{#if added}<div><dt>Added</dt><dd>{added}</dd></div>{/if}
				<div><dt>Source</dt><dd>Calibre</dd></div>
			</dl>
		</aside>
	</div>
</article>

<style>
	.book {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 1.35rem var(--page-h) 4rem;
		animation: fadeUp 0.6s var(--ease-out) both;
	}

	.crumb {
		font-family: var(--f-mono);
		font-size: 0.7rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		padding-bottom: 1.15rem;
		border-bottom: var(--border);
		margin-bottom: 1.05rem;
	}
	.crumb a {
		text-decoration: none;
		color: var(--muted);
	}
	.crumb a:hover {
		color: var(--clay-deep);
	}
	.crumb .sep {
		color: var(--faint);
		margin: 0 0.55rem;
	}
	.crumb .here {
		color: var(--ink);
	}

	.review-slot {
		margin-bottom: 1.6rem;
	}

	.masthead {
		grid-area: masthead;
		margin-bottom: 2rem;
	}
	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.6rem, 6vw, 4.4rem);
		line-height: 1;
		letter-spacing: -0.015em;
		margin: 0;
		overflow-wrap: break-word;
	}
	.subtitle {
		font-family: var(--f-serif);
		font-weight: 400;
		font-size: 1.25rem;
		margin: 0.9rem 0 0;
		max-width: 42rem;
	}
	.byline {
		font-family: var(--f-grotesk);
		font-size: 1rem;
		color: var(--muted);
		margin: 1rem 0 0;
	}
	.byline b {
		color: var(--ink);
		font-weight: 500;
	}

	/* Book-level theme chips under the byline — few enough to show in full (they
	   reuse the recipe-index .chip styles below, without the single-line clip). */
	.book-tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
		list-style: none;
		margin: 1.1rem 0 0;
		padding: 0;
	}

	.cols {
		display: grid;
		grid-template-columns: 1fr 332px;
		grid-template-rows: auto 1fr;
		grid-template-areas:
			'masthead aside'
			'reading aside';
		column-gap: 4rem;
		align-items: start;
	}
	.reading {
		grid-area: reading;
	}

	.lede {
		font-family: var(--f-serif);
		font-size: 1.12rem;
		line-height: 1.75;
		color: var(--ink);
		max-width: 40rem;
		margin: 0;
	}
	.lede p {
		margin: 0;
	}
	.lede.clamped p {
		display: -webkit-box;
		-webkit-line-clamp: 6;
		line-clamp: 6;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.readmore {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--clay-deep);
		background: none;
		border: none;
		border-bottom: 1px solid transparent;
		padding: 0;
		margin-top: 0.55rem;
		cursor: pointer;
	}
	.readmore:hover {
		border-bottom-color: var(--clay);
	}

	.rlabel {
		margin: 2rem 0 0.85rem;
	}

	.index {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.index li {
		padding: 0.9rem 0;
		border-top: var(--border);
	}
	.index li:first-child {
		border-top: var(--border-strong);
	}
	/* The row's text and its read toggle share a line; the toggle holds the right
	   edge so the ticks line up down the index. */
	.entry {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 1rem;
		align-items: baseline;
	}
	.rname {
		font-family: var(--f-serif);
		font-size: 1.12rem;
		line-height: 1.3;
	}
	.rname a {
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}
	.rname a:hover {
		color: var(--clay-deep);
	}
	/* Keep tags to a single line: extra chips wrap, then the second row clips away. */
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.45rem;
		max-height: 1.3rem;
		overflow: hidden;
	}
	.chip {
		display: inline-block;
		font-family: var(--f-grotesk);
		font-size: 0.68rem;
		font-weight: 500;
		line-height: 1.2;
		letter-spacing: 0.01em;
		padding: 0.18rem 0.5rem;
		border-radius: 3px;
		white-space: nowrap;
		text-decoration: none;
		background: var(--chip-clay);
		color: var(--chip-clay-c);
	}
	.chip.b {
		background: var(--chip-blue);
		color: var(--chip-blue-c);
	}
	.chip.g {
		background: var(--chip-green);
		color: var(--chip-green-c);
	}
	.chip:hover,
	.chip:focus-visible {
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.chip:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: 1px;
	}

	.more {
		font-family: var(--f-mono);
		font-size: 0.74rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		border-top: var(--border);
		padding-top: 1rem;
		margin: 0;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		margin: 1.1rem 0 0;
	}

	aside {
		grid-area: aside;
		position: sticky;
		top: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.75rem;
	}
	.plate {
		position: relative;
		aspect-ratio: 2 / 3;
		background: var(--bg-warm);
		border: var(--border);
		border-radius: 2px;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.cover {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.plate-title {
		font-family: var(--f-serif);
		font-style: italic;
		font-weight: 300;
		font-size: 1.5rem;
		line-height: 1.3;
		text-align: center;
		padding: 1.6rem 1.4rem;
	}
	.count-badge {
		position: absolute;
		top: 0.7rem;
		right: 0.7rem;
		min-width: 2.2rem;
		height: 2.2rem;
		padding: 0 0.55rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 999px;
		background: var(--clay);
		color: var(--bg);
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.82rem;
		line-height: 1;
		box-shadow: 0 0 0 2.5px var(--bg);
	}

	.actions {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	/* The two reading modes sit above every other action, in progress order. */
	.actions > :global(*:not(.read-epub):not(.read-recipes)) {
		order: 3;
	}
	.btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		padding: 0.7rem 1rem;
		border-radius: 3px;
		text-align: center;
		text-decoration: none;
		cursor: pointer;
		border: 1px solid transparent;
		display: flex;
		align-items: center;
		justify-content: space-between;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.btn .ar {
		font-weight: 400;
	}
	.btn.primary {
		background: var(--ink);
		color: var(--bg);
	}
	.btn.primary:hover {
		background: var(--ink-deep);
	}
	.btn.primary .ar {
		color: var(--bg);
		font-weight: 400;
	}
	.btn.ghost {
		background: transparent;
		color: var(--ink);
		border-color: var(--line-strong);
	}
	.btn.ghost:hover {
		border-color: var(--clay);
		color: var(--clay-deep);
	}
	.btn.danger {
		background: #b3402a;
		color: var(--bg);
		justify-content: center;
	}
	.btn.danger:hover {
		background: #9a3623;
	}

	.confirm {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		padding: 0.9rem;
		border: 1px solid var(--line-strong);
		border-radius: 3px;
	}
	.confirm .prompt {
		font-family: var(--f-serif);
		font-size: 0.98rem;
		line-height: 1.45;
		color: var(--muted);
		margin: 0;
	}
	.scope {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		border: none;
		margin: 0;
		padding: 0;
	}
	.scope legend {
		font-family: var(--f-mono);
		font-size: 0.64rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
		padding: 0 0 0.4rem;
	}
	.exclude {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--ink);
		cursor: pointer;
	}
	.exclude input {
		accent-color: var(--clay);
		margin-top: 0.15rem;
	}

	dl.meta {
		margin: 0;
		border-top: var(--border-strong);
	}
	dl.meta div {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 1rem;
		align-items: baseline;
		padding: 0.62rem 0;
		border-bottom: var(--border);
	}
	dl.meta dt {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}
	dl.meta dd {
		margin: 0;
		font-family: var(--f-mono);
		font-size: 0.8rem;
		letter-spacing: 0;
		text-align: right;
	}
	/* Read progress: the percentage leads, the fraction sits behind it as the
	   quieter half of the figure. */
	dd.read .pct {
		color: var(--clay-deep);
	}
	dd.read .of {
		color: var(--muted);
		margin-left: 0.5rem;
	}

	@media (max-width: 900px) {
		.cols {
			grid-template-columns: 1fr;
			grid-template-rows: none;
			grid-template-areas:
				'masthead'
				'aside'
				'reading';
			row-gap: 2.5rem;
		}
		.masthead {
			margin-bottom: 0;
		}
		aside {
			position: static;
			display: grid;
			grid-template-columns: 150px 1fr;
			gap: 1.5rem;
			align-items: start;
		}
		.actions,
		dl.meta {
			grid-column: 1 / -1;
		}
	}
	@media (max-width: 520px) {
		aside {
			grid-template-columns: 1fr;
		}
		.plate {
			max-width: 170px;
		}
	}
</style>
