<script module lang="ts">
	export type BookOfTheDay = {
		id: string;
		title: string;
		author: string;
		description: string;
		recipeCount: number;
		hasCover: boolean;
	};

	/** A book the reader is part-way through. */
	export type ContinueBook = {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		seenCount: number;
		hasCover: boolean;
	};

	/** Library-wide reading progress: recipes seen against the whole collection. */
	export type ReadProgress = { recipes: number; recipesSeen: number };
</script>

<script lang="ts">
	import { plainText } from '$lib/html';
	import { readPercent } from '$lib/progress';
	import { cleanTitle } from '$lib/title';

	let {
		bookOfTheDay,
		progress = { recipes: 0, recipesSeen: 0 },
		continueReading = []
	}: {
		bookOfTheDay: BookOfTheDay | null;
		progress?: ReadProgress;
		continueReading?: ContinueBook[];
	} = $props();

	const nf = new Intl.NumberFormat('en-GB');
	let coverFailed = $state(false);
	let showCover = $derived(!!bookOfTheDay?.hasCover && !coverFailed);

	let title = $derived(bookOfTheDay ? cleanTitle(bookOfTheDay.title) : '');
	let description = $derived(bookOfTheDay ? plainText(bookOfTheDay.description) : '');

	// An empty library has no percentage to report, rather than 0% or NaN.
	let readPct = $derived(readPercent(progress.recipesSeen, progress.recipes));
</script>

<div
	class="home"
	data-verify-unit="home-landing"
	data-verify-has-feature={bookOfTheDay ? 'true' : 'false'}
	data-verify-read-pct={readPct === null ? '' : readPct}
	data-verify-continue-count={continueReading.length}
>
	{#if bookOfTheDay}
		<section class="feature">
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
				<h1 class="feature-title">
					<a href={`/books/${bookOfTheDay.id}`}>{title}</a>
				</h1>
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
	{:else}
		<p class="empty">No books yet.</p>
	{/if}

	{#if readPct !== null}
		<section class="progress-block">
			<p class="label">Read so far</p>
			<p class="figure">
				<span class="pct">{readPct}%</span>
				<span class="of mono"
					>{nf.format(progress.recipesSeen)} of {nf.format(progress.recipes)} recipes</span
				>
			</p>
			<div class="rule" aria-hidden="true">
				<span class="rule-fill" style:width={`${readPct}%`}></span>
			</div>
		</section>
	{/if}

	{#if continueReading.length}
		<section class="continue">
			<p class="label">Continue reading</p>
			<ul class="strip">
				{#each continueReading as book (book.id)}
					{@const pct = readPercent(book.seenCount, book.recipeCount) ?? 0}
					<li>
						<a class="cbook" href={`/books/${book.id}`}>
							<span class="cbook-title">{cleanTitle(book.title)}</span>
							<span class="cbook-author">{book.author}</span>
						</a>
						<div class="rule" aria-hidden="true">
							<span class="rule-fill" style:width={`${pct}%`}></span>
						</div>
						<p class="cbook-meta mono">{book.seenCount} of {book.recipeCount} · {pct}%</p>
					</li>
				{/each}
			</ul>
		</section>
	{/if}
</div>

<style>
	.home {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}

	.feature {
		display: grid;
		grid-template-columns: 280px 1fr;
		gap: clamp(2rem, 5vw, 4.5rem);
		align-items: center;
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
		border-color: var(--clay);
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

	.feature-meta {
		min-width: 0;
		max-width: 40rem;
	}

	.feature-title {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 4.5vw, 3.4rem);
		line-height: 1.08;
		letter-spacing: -0.01em;
		margin: 0.6rem 0 0.4rem;
		overflow-wrap: break-word;
	}

	.feature-title a {
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}

	.feature-title a:hover {
		color: var(--clay-deep);
	}

	.feature-author {
		font-family: var(--f-grotesk);
		font-size: 1.02rem;
		color: var(--muted);
		margin: 0;
	}

	.feature-desc {
		font-family: var(--f-serif);
		font-size: 1.12rem;
		line-height: 1.6;
		color: var(--ink);
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
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.92rem;
		color: var(--ink);
		text-decoration: none;
		border-bottom: 2px solid var(--clay);
		padding-bottom: 2px;
		transition: color 0.18s var(--ease-out);
	}

	.cta:hover {
		color: var(--clay-deep);
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.4rem;
		color: var(--muted);
	}

	/* Reading progress — the library ledger's one figure, and the books it came from. */
	.progress-block {
		margin-top: 4.5rem;
		padding-top: 1.6rem;
		border-top: var(--border-strong);
		max-width: 26rem;
	}

	.figure {
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		margin: 0.8rem 0 0.9rem;
	}

	.pct {
		font-family: var(--f-serif);
		font-size: 2.4rem;
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
		background: var(--clay);
	}

	.continue {
		margin-top: 3.5rem;
	}

	.strip {
		list-style: none;
		margin: 1.1rem 0 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--col-gap);
	}

	.strip li {
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
	}

	.cbook {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		text-decoration: none;
	}

	.cbook-title {
		font-family: var(--f-serif);
		font-size: 1.05rem;
		line-height: 1.25;
		transition: color 0.18s var(--ease-out);
	}

	.cbook:hover .cbook-title {
		color: var(--clay-deep);
	}

	.cbook-author {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		color: var(--muted);
	}

	.cbook-meta {
		color: var(--faint);
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
		.feature {
			grid-template-columns: 150px 1fr;
			gap: 1.5rem;
			align-items: start;
		}
	}

	@media (max-width: 560px) {
		/* Mobile: drop the cover entirely so the feature reads as a text-led
		   "book of the day" — the archive is text-first (DESIGN §7), and a lone
		   full-width cover left the page feeling lopsided. */
		.feature {
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
		.progress-block {
			margin-top: 3rem;
		}
		.strip {
			grid-template-columns: 1fr;
			gap: 1.5rem;
		}
	}
</style>
