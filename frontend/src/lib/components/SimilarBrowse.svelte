<script module lang="ts">
	import type { RecipeRowData } from './RecipeRow.svelte';
	import type { ListMembership, ListPanelApi } from '$lib/api/lists';

	export type SimilarBrowseData = {
		/** The recipe the list is "similar to" — for the heading and the link back. */
		recipeId: string;
		recipeName: string;
		recipes: RecipeRowData[];
		/** 'vector' = nearest by embedding, 'keyword' = the shared-keyword fallback. */
		basis: 'vector' | 'keyword';
	};

	/** The selection bar's lists + bulk callbacks — the route owns the IO. */
	export type BrowseSelectionTools = {
		lists: ListMembership[];
		onAdd: (listId: string, recipeIds: string[]) => void;
		onCreate: (name: string, recipeIds: string[]) => void;
	};

	export type SimilarBrowseProps = SimilarBrowseData & {
		selection?: BrowseSelectionTools;
		listPicker?: { api?: ListPanelApi };
	};
</script>

<script lang="ts">
	import RecipeRow from './RecipeRow.svelte';
	import SelectionBar from './SelectionBar.svelte';

	let { recipeId, recipeName, recipes, basis, selection, listPicker }: SimilarBrowseProps =
		$props();

	// Selection mode: local to this surface, cleared when the row set changes
	// (client nav between "similar to" sources reuses this component).
	let selectMode = $state(false);
	let selectedRows = $state<string[]>([]);

	$effect(() => {
		void recipes;
		selectedRows = [];
	});

	function toggleSelectMode() {
		selectMode = !selectMode;
		if (!selectMode) selectedRows = [];
	}

	function toggleRow(id: string, on: boolean) {
		selectedRows = on ? [...selectedRows, id] : selectedRows.filter((r) => r !== id);
	}
</script>

<section
	class="browse"
	data-verify-unit="similar-browse"
	data-verify-count={recipes.length}
	data-verify-basis={basis}
	data-verify-select-mode={selectMode ? 'true' : 'false'}
	data-verify-selected={selectedRows.length}
	aria-labelledby="browse-heading"
>
	<nav class="crumb" aria-label="Breadcrumb">
		<a href="/recipes">Recipes</a><span class="sep">›</span><a href={`/recipes/${recipeId}`}
			>{recipeName}</a
		><span class="sep">›</span><span class="here">Similar</span>
	</nav>

	<div class="headrow">
		<h1 class="display" id="browse-heading">
			Similar to <span class="src">{recipeName}</span>
		</h1>
		{#if selection && recipes.length}
			<button
				class="select-toggle"
				type="button"
				aria-pressed={selectMode}
				onclick={toggleSelectMode}
			>
				Select
			</button>
		{/if}
	</div>

	{#if selection && selectMode}
		<SelectionBar
			count={selectedRows.length}
			total={recipes.length}
			allSelected={recipes.length > 0 && selectedRows.length === recipes.length}
			lists={selection.lists}
			onSelectAll={() => (selectedRows = recipes.map((r) => r.id))}
			onClear={() => (selectedRows = [])}
			onAdd={(listId) => selection?.onAdd(listId, selectedRows)}
			onCreate={(name) => selection?.onCreate(name, selectedRows)}
		/>
	{/if}

	{#if recipes.length}
		<ul class="rows">
			{#each recipes as r (r.id)}
				<RecipeRow
					{...r}
					{listPicker}
					selectable={selectMode}
					selected={selectedRows.includes(r.id)}
					onSelect={(on) => toggleRow(r.id, on)}
				/>
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

	.headrow {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1rem;
		margin: 1.1rem 0 2.25rem;
	}

	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-size: clamp(2rem, 4vw, 3rem);
		line-height: 1.05;
		letter-spacing: -0.015em;
		margin: 0;
	}

	.select-toggle {
		flex: none;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.8rem;
		color: var(--ink);
		background: none;
		border: var(--border);
		border-radius: 3px;
		padding: 0.35rem 0.75rem;
		cursor: pointer;
		margin-bottom: 0.4rem;
		transition:
			border-color 0.16s var(--ease-out),
			background 0.16s var(--ease-out),
			color 0.16s var(--ease-out);
	}
	.select-toggle:hover {
		border-color: var(--clay);
	}
	.select-toggle[aria-pressed='true'] {
		background: var(--clay);
		border-color: var(--clay);
		color: var(--bg);
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
