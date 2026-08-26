<script module lang="ts">
	export type BookOfTheDay = {
		id: string;
		title: string;
		author: string;
		description: string;
		recipeCount: number;
		hasCover: boolean;
	};

	/** A book part-way through, in the mode it was last read in. */
	export type ContinueBook = {
		id: string;
		title: string;
		author: string;
		mode: 'book' | 'recipes';
		fraction: number;
		/** The recipe both modes pick back up at, once one has been reached. */
		resumeRecipeId: string | null;
		hasCover: boolean;
	};

	/** Back into the mode this book was left in — its pages, or the recipe it reached. */
	function resumeHref(book: ContinueBook): string {
		return book.mode === 'recipes' && book.resumeRecipeId
			? `/recipes/${book.resumeRecipeId}?context=book`
			: `/books/${book.id}/read`;
	}

	/** A book queued to read next — not yet being read, so no resume semantics. */
	export type UpNextBook = {
		id: string;
		title: string;
		author: string;
		hasCover: boolean;
		recipeCount: number;
	};

	/** A recipe opened recently — the trail back to where reading left off. */
	export type RecentRecipe = {
		id: string;
		name: string;
		bookId: string;
		bookTitle: string;
	};

	/** Library-wide reading: books read through against the whole collection. */
	export type ReadProgress = { books: number; booksRead: number };
</script>

<script lang="ts">
	import BookCard from '$lib/components/BookCard.svelte';
	import { plainText } from '$lib/html';
	import { readPercent } from '$lib/progress';
	import { cleanTitle } from '$lib/title';

	let {
		bookOfTheDay,
		progress = { books: 0, booksRead: 0 },
		continueReading = [],
		upNext = [],
		recentlyRead = []
	}: {
		bookOfTheDay: BookOfTheDay | null;
		progress?: ReadProgress;
		continueReading?: ContinueBook[];
		upNext?: UpNextBook[];
		recentlyRead?: RecentRecipe[];
	} = $props();

	const nf = new Intl.NumberFormat('en-GB');
	let coverFailed = $state(false);
	let showCover = $derived(!!bookOfTheDay?.hasCover && !coverFailed);

	let title = $derived(bookOfTheDay ? cleanTitle(bookOfTheDay.title) : '');
	let description = $derived(bookOfTheDay ? plainText(bookOfTheDay.description) : '');

	// An empty library has no percentage to report, rather than 0% or NaN.
	let readPct = $derived(readPercent(progress.booksRead, progress.books));

	// Books in progress are what brings you back, so they lead the page and take the
	// masthead. With nothing part-read the feature leads instead, as it always did.
	let lead = $derived(
		continueReading.length ? 'continue' : bookOfTheDay ? 'feature' : 'empty'
	);
</script>

<div
	class="home"
	data-verify-unit="home-landing"
	data-verify-has-feature={bookOfTheDay ? 'true' : 'false'}
	data-verify-read-pct={readPct === null ? '' : readPct}
	data-verify-continue-count={continueReading.length}
	data-verify-upnext-count={upNext.length}
	data-verify-recent-count={recentlyRead.length}
	data-verify-lead={lead}
>
	{#if continueReading.length}
		<section class="continue">
			<h1 class="display">Continue reading</h1>
			<ul class="strip">
				{#each continueReading as book, i (book.id)}
					{@const pct = Math.round(book.fraction * 100)}
					<li class="cell" style={`animation-delay: ${Math.min(i * 60, 240)}ms`}>
						<BookCard
							id={book.id}
							title={book.title}
							author={book.author}
							hasCover={book.hasCover}
							href={resumeHref(book)}
							progress={book.fraction}
							showCount={false}
						/>
						<p class="cbook-meta mono">{pct}% through</p>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if bookOfTheDay}
		<section class="feature" class:secondary={lead === 'continue'}>
			<a class="feature-plate" href={`/books/${bookOfTheDay.id}`} aria-label={title}>
				<div class="plate">
					{#if showCover}
						<img
							class="cover"
							src={`/api/books/${bookOfTheDay.id}/cover`}
							alt={`Cover of ${title}`}
							onerror={() => (coverFailed = true)}
						/>
					{:else}
						<span class="plate-title" aria-hidden="true">{title}</span>
					{/if}
				</div>
			</a>
			<div class="feature-meta">
				<p class="label">Book of the day</p>
				<!-- The lead section owns the page's h1; demoted when the strip leads. -->
				<svelte:element this={lead === 'continue' ? 'h2' : 'h1'} class="feature-title">
					<a href={`/books/${bookOfTheDay.id}`}>{title}</a>
				</svelte:element>
				<p class="feature-author">{bookOfTheDay.author}</p>
				{#if description}
					<p class="feature-desc">{description}</p>
				{/if}
				<p class="feature-count mono">
					{#if bookOfTheDay.recipeCount > 0}{nf.format(bookOfTheDay.recipeCount)} recipes{:else}—
						pending extraction{/if}
				</p>
				<a class="cta" href="/books">Browse all books →</a>
			</div>
		</section>
	{:else if lead === 'empty'}
		<p class="empty">No books yet.</p>
	{/if}

	{#if upNext.length}
		<!-- Never the lead: a queued book is a plan, not progress — whatever leads the
		     page keeps the masthead, and Up next reads as a quieter shelf below it. -->
		<section class="upnext">
			<h2 class="label">Up next</h2>
			<ul class="strip">
				{#each upNext as book, i (book.id)}
					<li class="cell" style={`animation-delay: ${Math.min(i * 60, 240)}ms`}>
						<BookCard
							id={book.id}
							title={book.title}
							author={book.author}
							hasCover={book.hasCover}
							recipeCount={book.recipeCount}
						/>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if recentlyRead.length}
		<section class="recent">
			<h2 class="label">Recently opened</h2>
			<ol class="recent-index">
				{#each recentlyRead as r, i (r.id)}
					<li>
						<span class="num mono" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
						<a class="rtitle" href={`/recipes/${r.id}`}>{r.name}</a>
						<a class="rbook" href={`/books/${r.bookId}`}>{cleanTitle(r.bookTitle)}</a>
					</li>
				{/each}
			</ol>
		</section>
	{/if}

	{#if readPct !== null}
		<section class="progress-block">
			<h2 class="label">Read so far</h2>
			<p class="figure">
				<span class="pct">{readPct}%</span>
				<span class="of mono"
					>{nf.format(progress.booksRead)} of {nf.format(progress.books)} books</span
				>
			</p>
			<div class="rule" aria-hidden="true">
				<span class="rule-fill" style:width={`${readPct}%`}></span>
			</div>
		</section>
	{/if}
</div>

<style>
	.home {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}

	/* Continue reading leads the page: a masthead and a cover grid, the same card
	   language as the library so a part-read book reads as the book it is. */
	.display {
		font-family: var(--f-grotesk);
		font-weight: 700;
		font-size: clamp(1.8rem, 4vw, 2.4rem);
		line-height: 1.05;
		letter-spacing: -0.02em;
		margin: 0 0 1.9rem;
	}

	.feature {
		display: grid;
		grid-template-columns: 280px 1fr;
		gap: clamp(2rem, 5vw, 4.5rem);
		align-items: center;
	}

	/* Behind the strip the feature is discovery, not the headline: a hairline above
	   it, a smaller plate, and a title that no longer competes with the masthead. */
	.feature.secondary {
		grid-template-columns: 190px 1fr;
		align-items: start;
		margin-top: 4.5rem;
		padding-top: 2.6rem;
		border-top: var(--border-strong);
	}

	.feature.secondary .feature-title {
		font-size: clamp(1.7rem, 2.6vw, 2.2rem);
	}

	.feature.secondary .feature-desc {
		font-size: 1.02rem;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		margin-top: 1rem;
	}

	.feature-plate {
		display: block;
		text-decoration: none;
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
		transition: border-color 0.2s var(--ease-out);
	}

	.feature-plate:hover .plate {
		border-color: var(--accent);
	}

	.cover {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.plate-title {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 1.3rem;
		line-height: 1.3;
		text-align: center;
		padding: 1.6rem 1.4rem;
	}

	.feature-meta {
		min-width: 0;
		max-width: 40rem;
	}

	.feature-title {
		font-family: var(--f-grotesk);
		font-weight: 700;
		font-size: clamp(2rem, 4vw, 2.9rem);
		line-height: 1.08;
		letter-spacing: -0.02em;
		margin: 0.6rem 0 0.4rem;
		overflow-wrap: break-word;
	}

	.feature-title a {
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}

	.feature-title a:hover {
		color: var(--accent-deep);
	}

	.feature-author {
		font-family: var(--f-mono);
		font-size: 0.74rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 0.2rem 0 0;
	}

	.feature-desc {
		font-family: var(--f-grotesk);
		font-size: 1.02rem;
		line-height: 1.6;
		color: var(--muted);
		max-width: 36rem;
		margin: 1.4rem 0 0;
		display: -webkit-box;
		-webkit-line-clamp: 6;
		line-clamp: 6;
		-webkit-box-orient: vertical;
		overflow: hidden;
		overflow-wrap: anywhere;
	}

	.feature-count {
		color: var(--faint);
		margin: 1.3rem 0 0;
	}

	.cta {
		display: inline-block;
		margin-top: 2rem;
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #fff;
		background: var(--accent);
		padding: 0.7rem 1.2rem;
		text-decoration: none;
		transition: background 0.18s var(--ease-out);
	}

	.cta:hover {
		background: var(--accent-deep);
	}

	.empty {
		font-family: var(--f-grotesk);
		font-size: 1.2rem;
		color: var(--muted);
	}

	/* The queue's shelf: same card language as the continue strip, under a quiet
	   mono label — a plan for later, not the page's headline. */
	.upnext {
		margin-top: 3.5rem;
		padding-top: 1.2rem;
		border-top: var(--rule);
	}
	.upnext h2 {
		margin: 0 0 1.1rem;
		font-weight: 400;
	}

	/* Where reading left off, as a numbered index (DESIGN §4): recipe name leading,
	   its book trailing in the quieter grotesque. */
	.recent {
		margin-top: 3.5rem;
		padding-top: 1.2rem;
		border-top: var(--rule);
	}
	.recent h2 {
		margin: 0 0 0.6rem;
		font-weight: 400;
	}
	.recent-index {
		list-style: none;
		margin: 0;
		padding: 0;
		max-width: 46rem;
	}
	.recent-index li {
		display: grid;
		grid-template-columns: 2.2rem 1fr auto;
		align-items: baseline;
		gap: 0.5rem 1rem;
		padding: 0.7rem 0;
		border-bottom: var(--border);
	}
	.recent-index .num {
		font-size: 0.72rem;
		color: var(--accent);
	}
	.rtitle {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.98rem;
		line-height: 1.3;
		color: var(--ink);
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}
	.rtitle:hover {
		color: var(--accent-deep);
	}
	.rbook {
		font-family: var(--f-mono);
		font-size: 0.66rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
		text-decoration: none;
		text-align: right;
	}
	.rbook:hover {
		color: var(--ink);
	}

	/* The library-wide figure closes the page — a ledger line, not a headline. */
	.progress-block {
		margin-top: 4rem;
		padding-top: 1.2rem;
		border-top: var(--rule);
		max-width: 26rem;
	}

	.progress-block h2 {
		margin: 0;
		font-weight: 400;
	}

	.figure {
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		margin: 0.7rem 0 0.8rem;
	}

	.pct {
		font-family: var(--f-grotesk);
		font-weight: 700;
		font-size: 1.7rem;
		line-height: 1;
		letter-spacing: -0.01em;
	}

	.of {
		color: var(--muted);
	}

	.rule {
		height: 3px;
		background: var(--line);
	}

	.rule-fill {
		display: block;
		height: 100%;
		background: var(--accent);
	}

	.strip {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		/* Cards keep a sane width whatever the strip holds — one part-read book must
		   not stretch to a quarter of the page, nor fill it. */
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 1.5rem var(--col-gap);
	}

	.cell {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		animation: fadeUp 0.6s var(--ease-out) both;
	}

	/* The card's rule is decorative; this line is the readable statement of progress,
	   so it carries body-text contrast rather than caption grey. */
	.cbook-meta {
		color: var(--muted);
		margin: 0;
	}

	@media (max-width: 760px) {
		.home {
			padding: 3rem var(--page-h);
		}
		.strip {
			grid-template-columns: repeat(2, 1fr);
			gap: 1.75rem 1.5rem;
		}
		.feature,
		.feature.secondary {
			grid-template-columns: 150px 1fr;
			gap: 1.5rem;
			align-items: start;
		}
	}

	@media (max-width: 560px) {
		/* Mobile: drop the cover entirely so the feature reads as a text-led
		   "book of the day" — the archive is text-first (DESIGN §7), and a lone
		   full-width cover left the page feeling lopsided. */
		.feature,
		.feature.secondary {
			grid-template-columns: 1fr;
			gap: 0;
		}
		.feature-plate {
			display: none;
		}
		.feature-meta {
			max-width: none;
		}
		.feature-title {
			font-size: clamp(2.3rem, 9vw, 3rem);
			margin-top: 0.2rem;
		}
		/* Demoted, it stays demoted: the masthead above it is the page's headline. */
		.feature.secondary .feature-title {
			font-size: clamp(1.6rem, 6.5vw, 2rem);
		}
		.progress-block {
			margin-top: 3rem;
		}
		/* The cards reshape into the library's text-first rows at this width, so the
		   strip becomes a hairline list rather than a column of plates. */
		.strip {
			grid-template-columns: 1fr;
			gap: 0;
			border-top: var(--border);
		}
		.cell {
			gap: 0;
			padding-bottom: 0.7rem;
			border-bottom: var(--border);
		}
		/* Aligns under the row's title, clear of the 46px thumbnail beside it. */
		.cbook-meta {
			padding-left: 3.9rem;
		}
	}
</style>
