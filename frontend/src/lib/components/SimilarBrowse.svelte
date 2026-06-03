<script module lang="ts">
	import type { RecipeRowData } from './RecipeRow.svelte';

	export type SimilarBrowseData = {
		/** The recipe the list is "similar to" — for the heading and the link back. */
		recipeId: string;
		recipeName: string;
		recipes: RecipeRowData[];
		/** 'vector' = nearest by embedding, 'keyword' = the shared-keyword fallback. */
		basis: 'vector' | 'keyword';
	};
</script>

<script lang="ts">
	import RecipeRow from './RecipeRow.svelte';

	let { recipeId, recipeName, recipes, basis }: SimilarBrowseData = $props();
</script>

<section
	class="browse"
	data-verify-unit="similar-browse"
	data-verify-count={recipes.length}
	data-verify-basis={basis}
	aria-labelledby="browse-heading"
>
	<nav class="crumb" aria-label="Breadcrumb">
		<a href="/recipes">Recipes</a><span class="sep">›</span><a href={`/recipes/${recipeId}`}
			>{recipeName}</a
		><span class="sep">›</span><span class="here">Similar</span>
	</nav>

	<h1 class="display" id="browse-heading">
		Similar to <span class="src">{recipeName}</span>
	</h1>

	{#if recipes.length}
		<ul class="rows">
			{#each recipes as r (r.id)}
				<RecipeRow {...r} />
			{/each}
		</ul>
	{:else}
		<p class="empty">No similar recipes found.</p>
	{/if}
</section>

<style>
	.browse {
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

	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-size: clamp(2rem, 4vw, 3rem);
		line-height: 1.05;
		letter-spacing: -0.015em;
		margin: 1.1rem 0 2.25rem;
	}
	.src {
		font-style: italic;
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: var(--border-strong);
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.15rem;
		color: var(--muted);
		margin: 0;
	}
</style>
