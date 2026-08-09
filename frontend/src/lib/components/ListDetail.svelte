<script module lang="ts">
	import type { RecipeRowData, RowPickerHook } from './RecipeRow.svelte';
	import type { ListMembership } from '$lib/api/lists';

	export type ListDetailData = {
		id: string;
		name: string;
		isDefault: boolean;
		recipeCount: number;
		recipes: RecipeRowData[];
	};

	/** The selection bar's lists + bulk callbacks — the route owns the IO. */
	export type ListSelectionTools = {
		lists: ListMembership[];
		onAdd: (listId: string, recipeIds: string[]) => void;
		onCreate: (name: string, recipeIds: string[]) => void;
		onRemove: (recipeIds: string[]) => void;
	};
</script>

<script lang="ts">
	import RecipeRow from './RecipeRow.svelte';
	import SelectionBar from './SelectionBar.svelte';

	type Props = {
		list: ListDetailData;
		onRename?: (name: string) => void;
		onDelete?: () => void;
		onRemoveRecipe?: (recipeId: string) => void;
		selection?: ListSelectionTools;
		listPicker?: RowPickerHook;
	};

	let { list, onRename, onDelete, onRemoveRecipe, selection, listPicker }: Props = $props();

	let mode = $state<'view' | 'rename' | 'confirm'>('view');
	let editName = $state('');
	let lastRemoved = $state('');
	let lastRenamed = $state('');
	let deleted = $state(false);

	// Selection mode: local to this surface. The row set changing (the route reloads
	// the list after a mutation) empties the selection.
	let selectMode = $state(false);
	let selectedRows = $state<string[]>([]);
	let bulkRemoved = $state('');

	// Key the clear on the row ids' *value* — an effect on the array itself refires
	// on unrelated interactions (deep-proxy invalidation) and wipes a live selection.
	let rowsKey = $derived(list.recipes.map((r) => r.id).join('|'));
	$effect(() => {
		void rowsKey;
		selectedRows = [];
	});

	function toggleSelectMode() {
		selectMode = !selectMode;
		if (!selectMode) selectedRows = [];
	}

	function toggleRow(id: string, on: boolean) {
		selectedRows = on ? [...selectedRows, id] : selectedRows.filter((r) => r !== id);
	}

	function bulkRemove() {
		bulkRemoved = String(selectedRows.length);
		selection?.onRemove(selectedRows);
	}

	function startRename() {
		editName = list.name;
		mode = 'rename';
	}

	function saveRename() {
		const next = editName.trim();
		if (next && next !== list.name) {
			lastRenamed = next;
			onRename?.(next);
		}
		mode = 'view';
	}

	function confirmDelete() {
		deleted = true;
		onDelete?.();
		mode = 'view';
	}

	function removeRecipe(id: string) {
		lastRemoved = id;
		onRemoveRecipe?.(id);
	}
</script>

<section
	class="list"
	data-verify-unit="list-detail"
	data-verify-id={list.id}
	data-verify-name={list.name}
	data-verify-default={list.isDefault ? 'true' : 'false'}
	data-verify-count={list.recipes.length}
	data-verify-empty={list.recipes.length === 0 ? 'true' : 'false'}
	data-verify-removed={lastRemoved}
	data-verify-renamed={lastRenamed}
	data-verify-deleted={deleted ? 'true' : 'false'}
	data-verify-select-mode={selectMode ? 'true' : 'false'}
	data-verify-selected={selectedRows.length}
	data-verify-bulk-removed={bulkRemoved}
>
	<nav class="crumb" aria-label="Breadcrumb">
		<a href="/lists">Lists</a><span class="sep">›</span><span class="here">{list.name}</span>
	</nav>

	<header class="masthead">
		{#if mode === 'rename'}
			<div class="rename">
				<input
					class="rename-input"
					type="text"
					aria-label={`Rename list ${list.name}`}
					value={editName}
					oninput={(e) => (editName = e.currentTarget.value)}
					onkeydown={(e) => {
						if (e.key === 'Enter') {
							e.preventDefault();
							saveRename();
						}
					}}
				/>
				<div class="actions">
					<button class="btn primary rename-save" type="button" onclick={saveRename}>Save</button>
					<button class="btn ghost" type="button" onclick={() => (mode = 'view')}>Cancel</button>
				</div>
			</div>
		{:else if mode === 'confirm'}
			<div class="confirm">
				<h1 class="display">{list.name}</h1>
				<p class="prompt">Delete this list? The recipes themselves are kept.</p>
				<div class="actions">
					<button class="btn danger confirm-delete" type="button" onclick={confirmDelete}>
						Delete list
					</button>
					<button class="btn ghost" type="button" onclick={() => (mode = 'view')}>Cancel</button>
				</div>
			</div>
		{:else}
			<div class="head">
				<div class="head-main">
					<h1 class="display">{list.name}</h1>
					<p class="meta mono">
						{list.recipes.length}
						{list.recipes.length === 1 ? 'recipe' : 'recipes'}
					</p>
				</div>
				{#if selection || !list.isDefault}
					<div class="actions">
						{#if selection}
							<button
								class="btn ghost select-toggle"
								type="button"
								aria-pressed={selectMode}
								onclick={toggleSelectMode}
							>
								Select
							</button>
						{/if}
						{#if !list.isDefault}
							<button class="btn ghost rename-btn" type="button" onclick={startRename}>
								Rename
							</button>
							<button class="btn ghost delete-btn" type="button" onclick={() => (mode = 'confirm')}>
								Delete
							</button>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</header>

	{#if selection && selectMode}
		<SelectionBar
			count={selectedRows.length}
			total={list.recipes.length}
			allSelected={list.recipes.length > 0 && selectedRows.length === list.recipes.length}
			lists={selection.lists}
			onSelectAll={() => (selectedRows = list.recipes.map((r) => r.id))}
			onClear={() => (selectedRows = [])}
			onAdd={(listId) => selection?.onAdd(listId, selectedRows)}
			onCreate={(name) => selection?.onCreate(name, selectedRows)}
			onRemove={bulkRemove}
			removeLabel="Remove from this list"
		/>
	{/if}

	{#if list.recipes.length === 0}
		<p class="empty">No recipes in this list yet.</p>
	{:else}
		<ul class="rows">
			{#each list.recipes as recipe (recipe.id)}
				<RecipeRow
					id={recipe.id}
					name={recipe.name}
					bookId={recipe.bookId}
					bookTitle={recipe.bookTitle}
					bookAuthor={recipe.bookAuthor}
					keywords={recipe.keywords}
					onRemove={() => removeRecipe(recipe.id)}
					{listPicker}
					selectable={selectMode}
					selected={selectedRows.includes(recipe.id)}
					onSelect={(on) => toggleRow(recipe.id, on)}
				/>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.list {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 1.35rem var(--page-h) 4rem;
	}
	.crumb {
		font-family: var(--f-mono);
		font-size: 0.7rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		padding-bottom: 1.15rem;
		border-bottom: var(--border);
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

	.masthead {
		margin: 1.05rem 0 2.5rem;
		padding-bottom: 2rem;
		border-bottom: var(--border-strong);
	}
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1.5rem;
		flex-wrap: wrap;
	}
	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3.4rem);
		line-height: 1.04;
		letter-spacing: -0.015em;
		margin: 0.35rem 0 0;
	}
	.meta {
		font-size: 0.78rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		margin: 0.85rem 0 0;
	}

	.actions {
		display: flex;
		gap: 0.6rem;
		flex: none;
	}
	.btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		padding: 0.55rem 0.95rem;
		border-radius: 3px;
		cursor: pointer;
		border: 1px solid transparent;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.btn.primary {
		background: var(--ink);
		color: var(--bg);
	}
	.btn.primary:hover {
		background: var(--ink-deep);
	}
	.btn.ghost {
		background: transparent;
		color: var(--ink);
		border-color: var(--line-strong);
	}
	.btn.ghost:hover {
		border-color: var(--clay);
		color: var(--clay-deep);
	}
	.btn.danger {
		background: #b3402a;
		color: var(--bg);
	}
	.btn.danger:hover {
		background: #9a3623;
	}

	.rename,
	.confirm {
		display: flex;
		flex-direction: column;
		gap: 1.1rem;
	}
	.rename-input {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: clamp(2rem, 4.5vw, 3rem);
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.1rem;
		max-width: 32rem;
	}
	.rename-input:focus {
		outline: none;
		border-bottom-color: var(--clay);
	}
	.prompt {
		font-family: var(--f-serif);
		font-size: 1.15rem;
		color: var(--muted);
		margin: 0;
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		padding: 2rem 0;
		margin: 0;
	}

	@media (max-width: 560px) {
		.actions {
			flex: 1 1 100%;
		}
	}
</style>
