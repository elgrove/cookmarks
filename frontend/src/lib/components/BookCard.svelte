<script lang="ts">
	import { cleanTitle } from '$lib/title';

	let {
		id,
		title,
		author,
		recipeCount = 0,
		hasCover,
		showCount = true,
		href = `/books/${id}`,
		progress = null
	}: {
		id: string;
		title: string;
		author: string;
		recipeCount?: number;
		hasCover: boolean;
		/** The count circle competes with the progress rule for the same clay, so
		 *  surfaces that state the count in words (the home strip) turn it off. */
		showCount?: boolean;
		/** Where the card leads; the book page unless a surface has somewhere better
		 *  (the continue strip goes straight back to where reading stopped). */
		href?: string;
		/** How far through the book the reader is, 0 to 1; null for one never opened. */
		progress?: number | null;
	} = $props();

	// Cards show the clean name only; the colon-subtitle is a detail-page affordance.
	let displayTitle = $derived(cleanTitle(title));

	let coverFailed = $state(false);
	let showCover = $derived(hasCover && !coverFailed);
	// Read progress rides the bottom edge of the cover plate as a clay rule; a book
	// nothing has been read from carries none.
	let readPct = $derived(progress === null ? null : Math.round(progress * 100));
	let started = $derived(readPct !== null && readPct > 0);
	// Extraction and reading state live on the cover as a count circle and a rule;
	// fold both into the link's accessible name since they are decorative.
	let linkLabel = $derived(
		started
			? `${displayTitle}, ${readPct}% read`
			: recipeCount === 0
				? displayTitle
				: `${displayTitle}, ${recipeCount} recipes`
	);
</script>

<article class="card">
	<!-- A single stretched link covers the whole card surface (cover plate + meta),
	     so a click anywhere navigates to the book. -->
	<a class="card-link" {href} aria-label={linkLabel}>
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
			{#if showCount && recipeCount > 0}
				<span class="count-badge" aria-hidden="true">{recipeCount}</span>
			{/if}
			{#if started}
				<span class="progress" aria-hidden="true">
					<span class="progress-fill" style:width={`${readPct}%`}></span>
				</span>
			{/if}
		</div>
	</a>
	<div class="meta">
		<h3 class="title">{displayTitle}</h3>
		<p class="author">{author}</p>
	</div>
	<!-- Mobile rows only (hidden on the desktop cover grid): recipe count + chevron. -->
	<span class="row-aside" aria-hidden="true">
		{#if showCount && recipeCount > 0}<span class="row-count">{recipeCount}</span>{/if}<span
			class="chev"
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

	/* Read progress: a hairline rule along the plate's bottom edge, filled in clay
	   as far as the book has been read. Absent until something has been read. */
	.progress {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 3px;
		background: var(--line);
	}

	.progress-fill {
		display: block;
		height: 100%;
		background: var(--clay);
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
		.row-aside {
			display: inline-flex;
		}
	}
</style>
