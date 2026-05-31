<script lang="ts">
	let {
		id,
		title,
		author,
		recipeCount,
		hasCover
	}: {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		hasCover: boolean;
	} = $props();

	let coverFailed = $state(false);
	let showCover = $derived(hasCover && !coverFailed);
	// Extraction state lives on the cover as a count circle; fold the count into the
	// link's accessible name since the circle itself is decorative.
	let linkLabel = $derived(recipeCount > 0 ? `${title}, ${recipeCount} recipes` : title);
</script>

<article class="card">
	<a class="plate-link" href={`/books/${id}`} aria-label={linkLabel}>
		<div class="plate">
			{#if showCover}
				<img
					class="cover"
					src={`/api/books/${id}/cover`}
					alt={`Cover of ${title}`}
					loading="lazy"
					onerror={() => (coverFailed = true)}
				/>
			{:else}
				<!-- §7: missing cover → hairline plate bearing the title in serif. -->
				<span class="plate-title" aria-hidden="true">{title}</span>
			{/if}
			{#if recipeCount > 0}
				<span class="count-badge" aria-hidden="true">{recipeCount}</span>
			{/if}
		</div>
	</a>
	<div class="meta">
		<h3 class="title"><a href={`/books/${id}`}>{title}</a></h3>
		<p class="author">{author}</p>
	</div>
</article>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: 0.7rem;
	}

	.plate-link {
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

	.plate-link:hover .plate {
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
	}

	.title a {
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}

	.title a:hover {
		color: var(--clay-deep);
	}

	.author {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		color: var(--muted);
		margin: 0;
	}
</style>
