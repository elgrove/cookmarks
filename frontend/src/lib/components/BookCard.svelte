<script lang="ts">
	import { cleanTitle } from '$lib/title';

	let {
		id,
		title,
		author,
		recipeCount,
		hasCover,
		keywords = []
	}: {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		hasCover: boolean;
		keywords?: string[];
	} = $props();

	// Cards show the clean name only; the colon-subtitle is a detail-page affordance.
	let displayTitle = $derived(cleanTitle(title));

	let coverFailed = $state(false);
	let showCover = $derived(hasCover && !coverFailed);
	// Extraction state lives on the cover as a count circle; fold the count into the
	// link's accessible name since the circle itself is decorative.
	let linkLabel = $derived(
		recipeCount > 0 ? `${displayTitle}, ${recipeCount} recipes` : displayTitle
	);

	// A glance of the book's themes; the full set lives on the detail page. Rotating
	// chip tints (DESIGN §3.1).
	const tints = ['clay', 'blue', 'green'] as const;
	let shownKeywords = $derived(keywords.slice(0, 3));
</script>

<article class="card">
	<!-- A single stretched link covers the whole card surface (cover plate + meta),
	     so a click anywhere navigates to the book. -->
	<a class="card-link" href={`/books/${id}`} aria-label={linkLabel}>
		<div class="plate">
			{#if showCover}
				<img
					class="cover"
					src={`/api/books/${id}/cover`}
					alt={`Cover of ${displayTitle}`}
					loading="lazy"
					onerror={() => (coverFailed = true)}
				/>
			{:else}
				<!-- §7: missing cover → hairline plate bearing the title in serif. -->
				<span class="plate-title" aria-hidden="true">{displayTitle}</span>
			{/if}
			{#if recipeCount > 0}
				<span class="count-badge" aria-hidden="true">{recipeCount}</span>
			{/if}
		</div>
	</a>
	<div class="meta">
		<h3 class="title">{displayTitle}</h3>
		<p class="author">{author}</p>
		{#if shownKeywords.length}
			<ul class="chips" aria-label="Keywords">
				{#each shownKeywords as kw, i (kw)}
					<li class={`chip chip-${tints[i % tints.length]}`}>{kw}</li>
				{/each}
			</ul>
		{/if}
	</div>
	<!-- Mobile rows only (hidden on the desktop cover grid): recipe count + chevron. -->
	<span class="row-aside" aria-hidden="true">
		{#if recipeCount > 0}<span class="row-count">{recipeCount}</span>{/if}<span class="chev"
			>›</span
		>
	</span>
</article>

<style>
	.card {
		/* Anchor for the stretched-link overlay so the whole surface navigates. */
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 0.7rem;
	}

	.card-link {
		display: block;
		text-decoration: none;
	}
	/* Stretched link: the anchor's ::after covers the whole card (plate + meta),
	   so a click anywhere navigates to the book. */
	.card-link::after {
		content: '';
		position: absolute;
		inset: 0;
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

	.card:hover .plate {
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
		font-size: 1.15rem;
		line-height: 1.3;
		text-align: center;
		color: var(--ink);
		padding: 1.4rem 1.2rem;
	}

	/* Recipe-count circle — how many recipes were extracted. Absent = unextracted. */
	.count-badge {
		position: absolute;
		top: 0.6rem;
		right: 0.6rem;
		min-width: 2.1rem;
		height: 2.1rem;
		padding: 0 0.5rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 999px;
		background: var(--clay);
		color: var(--bg);
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.8rem;
		line-height: 1;
		box-shadow: 0 0 0 2.5px var(--bg);
	}

	.meta {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.title {
		font-family: var(--f-serif);
		font-weight: 500;
		font-size: 1.02rem;
		line-height: 1.25;
		margin: 0;
		transition: color 0.18s var(--ease-out);
	}

	.card:hover .title {
		color: var(--clay-deep);
	}

	.author {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		color: var(--muted);
		margin: 0;
	}

	/* A single line of theme chips; extras wrap and the second row clips away. */
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		list-style: none;
		margin: 0.35rem 0 0;
		padding: 0;
		max-height: 1.25rem;
		overflow: hidden;
	}
	.chip {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.03em;
		padding: 0.12rem 0.42rem;
		border-radius: 3px;
		white-space: nowrap;
	}
	.chip-clay {
		background: var(--chip-clay);
		color: var(--chip-clay-c);
	}
	.chip-blue {
		background: var(--chip-blue);
		color: var(--chip-blue-c);
	}
	.chip-green {
		background: var(--chip-green);
		color: var(--chip-green-c);
	}

	/* Mobile-only count + chevron, sitting to the right of a text row. */
	.row-aside {
		display: none;
		flex: none;
		align-items: center;
		gap: 0.55rem;
		margin-left: 0.5rem;
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		white-space: nowrap;
	}

	.chev {
		font-size: 1.1rem;
		line-height: 1;
		color: var(--faint);
	}

	/* Mobile: the cover grid collapses to text-first rows — a small cover
	   thumbnail, title + author, and the recipe count on the right. */
	@media (max-width: 560px) {
		.card {
			flex-direction: row;
			align-items: center;
			gap: 0.9rem;
			padding: 0.85rem 0.1rem;
		}
		.card-link {
			flex: 0 0 auto;
			width: 46px;
		}
		.plate {
			border-radius: 2px;
		}
		.count-badge {
			display: none;
		}
		.meta {
			flex: 1 1 auto;
			min-width: 0;
			gap: 0.15rem;
		}
		.title {
			font-size: 1.02rem;
		}
		/* Keep the text rows clean — chips are a desktop-grid affordance only. */
		.chips {
			display: none;
		}
		.row-aside {
			display: inline-flex;
		}
	}
</style>
