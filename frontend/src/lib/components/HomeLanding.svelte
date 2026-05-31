<script module lang="ts">
	export type BookOfTheDay = {
		id: string;
		title: string;
		author: string;
		description: string;
		recipeCount: number;
		hasCover: boolean;
	};
</script>

<script lang="ts">
	let { bookOfTheDay }: { bookOfTheDay: BookOfTheDay | null } = $props();

	const nf = new Intl.NumberFormat('en-GB');
	let coverFailed = $state(false);
	let showCover = $derived(!!bookOfTheDay?.hasCover && !coverFailed);

	// Calibre descriptions carry HTML; show a plain-text excerpt.
	function plainText(html: string): string {
		if (typeof DOMParser === 'undefined') return html;
		return (new DOMParser().parseFromString(html, 'text/html').body.textContent ?? '')
			.replace(/_{3,}/g, ' ') // collapse Calibre separator underscore runs
			.replace(/\s+/g, ' ')
			.trim();
	}
	let description = $derived(bookOfTheDay ? plainText(bookOfTheDay.description) : '');
</script>

<div
	class="home"
	data-verify-unit="home-landing"
	data-verify-has-feature={bookOfTheDay ? 'true' : 'false'}
>
	{#if bookOfTheDay}
		<section class="feature">
			<a class="feature-plate" href={`/books/${bookOfTheDay.id}`} aria-label={bookOfTheDay.title}>
				<div class="plate">
					{#if showCover}
						<img
							class="cover"
							src={`/api/books/${bookOfTheDay.id}/cover`}
							alt={`Cover of ${bookOfTheDay.title}`}
							onerror={() => (coverFailed = true)}
						/>
					{:else}
						<span class="plate-title" aria-hidden="true">{bookOfTheDay.title}</span>
					{/if}
				</div>
			</a>
			<div class="feature-meta">
				<p class="label">Book of the day</p>
				<h1 class="feature-title">
					<a href={`/books/${bookOfTheDay.id}`}>{bookOfTheDay.title}</a>
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
</div>

<style>
	.home {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 3rem var(--page-h) 5rem;
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

	@media (max-width: 760px) {
		.home {
			padding: 3rem var(--page-h);
		}
		.feature {
			grid-template-columns: 150px 1fr;
			gap: 1.5rem;
			align-items: start;
		}
	}

	@media (max-width: 520px) {
		.feature {
			grid-template-columns: 1fr;
		}
		.feature-plate {
			max-width: 200px;
		}
	}
</style>
