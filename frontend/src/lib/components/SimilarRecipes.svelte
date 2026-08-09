<script module lang="ts">
	import type { RecipeRowData, RowPickerHook } from './RecipeRow.svelte';

	export type SimilarRecipesData = {
		recipes: RecipeRowData[];
		/** How the neighbours were found — 'vector' = nearest by embedding, 'keyword' =
		 *  the shared-keyword fallback. Surfaced in the contract, not to the reader. */
		basis: 'vector' | 'keyword';
		/** When set, render a "More like this" link to the fuller similar list. */
		moreHref?: string;
	};

	export type SimilarRecipesProps = SimilarRecipesData & {
		/** Switches on the per-row add-to-list picker (no selection mode here). */
		listPicker?: RowPickerHook;
	};
</script>

<script lang="ts">
	import RecipeRow from './RecipeRow.svelte';

	let { recipes, basis, moreHref, listPicker }: SimilarRecipesProps = $props();
</script>

<section
	class="similar"
	data-verify-unit="similar-recipes"
	data-verify-count={recipes.length}
	data-verify-basis={basis}
	aria-labelledby="similar-heading"
>
	<h2 class="label" id="similar-heading">Similar recipes</h2>
	{#if recipes.length}
		<ul class="rows">
			{#each recipes as r (r.id)}
				<RecipeRow {...r} {listPicker} />
			{/each}
		</ul>
		{#if moreHref}
			<a class="more" href={moreHref}>More like this <span aria-hidden="true">→</span></a>
		{/if}
	{:else}
		<p class="empty">No similar recipes found.</p>
	{/if}
</section>

<style>
	.similar {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 0 var(--page-h) 4rem;
	}

	/* The global .label supplies the mono supra-label styling; this only spaces it. */
	.label {
		margin: 0 0 1.1rem;
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
		font-size: 1.1rem;
		color: var(--muted);
		margin: 0;
	}

	.more {
		display: inline-block;
		margin-top: 1.4rem;
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--clay-deep);
		text-decoration: none;
		border-bottom: 1px solid transparent;
		transition: border-color 0.18s var(--ease-out);
	}
	.more:hover {
		border-bottom-color: var(--clay);
	}
</style>
