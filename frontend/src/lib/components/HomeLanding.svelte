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

</script>

<script lang="ts">
	import BookCard from '$lib/components/BookCard.svelte';
	import { plainText } from '$lib/html';
	import { cleanTitle } from '$lib/title';

	let {
		bookOfTheDay,
		continueReading = []
	}: {
		bookOfTheDay: BookOfTheDay | null;
		continueReading?: ContinueBook[];
	} = $props();

	const nf = new Intl.NumberFormat('en-GB');
	let coverFailed = $state(false);
	let showCover = $derived(!!bookOfTheDay?.hasCover && !coverFailed);

	let title = $derived(bookOfTheDay ? cleanTitle(bookOfTheDay.title) : '');
	let description = $derived(bookOfTheDay ? plainText(bookOfTheDay.description) : '');

	// The book of the day is the first stop; the continue shelf follows it when present.
	let lead = $derived(
		bookOfTheDay ? 'feature' : continueReading.length ? 'continue' : 'empty'
	);
</script>

<div
	class="home"
	data-verify-unit="home-landing"
	data-verify-has-feature={bookOfTheDay ? 'true' : 'false'}
	data-verify-continue-count={continueReading.length}
	data-verify-lead={lead}
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
				<!-- The book of the day leads the home page. -->
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
	{:else if lead === 'empty'}
		<p class="empty">No books yet.</p>
	{/if}

	{#if continueReading.length}
		<section class="continue">
			<svelte:element this={lead === 'continue' ? 'h1' : 'h2'} class="display">
				Continue reading
			</svelte:element>
			<ul class="strip">
				{#each continueReading as book, i (book.id)}
					{@const pct = Math.round(book.fraction * 100)}
					<li class="cell" style={`animation-delay: ${Math.min(i * 60, 240)}ms`}>
						<BookCard
							id={book.id}
							title={book.title}
							author={book.author}
							hasCover={book.hasCover}
							href={`/books/${book.id}`}
							coverHref={resumeHref(book)}
							progress={book.fraction}
							showCount={false}
						/>
						<p class="cbook-meta mono">{pct}% through</p>
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
		grid-template-columns: 190px 1fr;
		gap: clamp(1.5rem, 4vw, 3rem);
		align-items: start;
	}

	.feature + .continue {
		margin-top: 4.5rem;
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
		font-size: clamp(1.7rem, 2.6vw, 2.2rem);
		line-height: 1.08;
		letter-spacing: -0.02em;
		margin: 0.4rem 0 0.3rem;
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
		max-width: 34rem;
		margin: 1rem 0 0;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
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
		margin-top: 1.3rem;
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--bg);
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
		.feature {
			grid-template-columns: 150px 1fr;
			gap: 1.5rem;
			align-items: start;
		}
		.feature + .continue {
			margin-top: 3.5rem;
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
			font-size: clamp(1.9rem, 7vw, 2.3rem);
			margin-top: 0.2rem;
		}
		.feature + .continue {
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
