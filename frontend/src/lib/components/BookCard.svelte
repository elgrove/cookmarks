<script lang="ts">
	let {
		id,
		title,
		author,
		recipeCount,
		hasCover,
		accession
	}: {
		id: string;
		title: string;
		author: string;
		recipeCount: number;
		hasCover: boolean;
		accession: string;
	} = $props();

	let pending = $derived(recipeCount === 0);
	let coverFailed = $state(false);
	let showCover = $derived(hasCover && !coverFailed);
</script>

<article class="card" data-card-pending={pending ? 'true' : 'false'}>
	<a class="plate-link" href={`/books/${id}`} aria-label={title}>
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
				<!-- §7: missing cover → hairline plate bearing the title in serif. Decorative
				     (the real title is in the meta below), so hidden from assistive tech. -->
				<span class="plate-title" aria-hidden="true">{title}</span>
			{/if}
			<span class="accession mono">{accession}</span>
		</div>
	</a>
	<div class="meta">
		<h3 class="title"><a href={`/books/${id}`}>{title}</a></h3>
		<p class="author">{author}</p>
		<p class="count mono">
			{#if pending}— pending extraction{:else}{recipeCount}
				{recipeCount === 1 ? 'recipe' : 'recipes'}{/if}
		</p>
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

	.accession {
		position: absolute;
		top: 0.5rem;
		left: 0.5rem;
		font-size: 0.6rem;
		color: var(--clay-deep);
		background: color-mix(in srgb, var(--bg) 82%, transparent);
		padding: 0.12rem 0.36rem;
		border-radius: 2px;
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

	.count {
		color: var(--faint);
		margin: 0.2rem 0 0;
	}
</style>
