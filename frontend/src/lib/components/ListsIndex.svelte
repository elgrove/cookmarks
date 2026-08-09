<script module lang="ts">
	import type { ListSummary } from '$lib/api/lists';

	export type ListsIndexProps = {
		lists: ListSummary[];
		/** Books on the reading queue — drives the pinned queue card. */
		queueCount?: number;
		onCreate?: (name: string) => void;
		onRename?: (id: string, name: string) => void;
		onDelete?: (id: string) => void;
	};
</script>

<script lang="ts">
	import ListCard from './ListCard.svelte';

	let { lists, queueCount = 0, onCreate, onRename, onDelete }: ListsIndexProps = $props();

	let search = $state('');
	let newName = $state('');
	let showCreate = $state(false);
	let createInputEl = $state<HTMLInputElement>();
	// Echoes of the last mutation, so the harness can verify wiring in isolation.
	let lastCreated = $state('');
	let lastRenamed = $state('');
	let lastDeleted = $state('');

	let query = $derived(search.trim().toLowerCase());

	// The default Favourites stays pinned first; the rest follow the incoming order.
	let visible = $derived(
		query ? lists.filter((l) => l.name.toLowerCase().includes(query)) : lists
	);

	let countLabel = $derived(query ? `${visible.length} of ${lists.length}` : `${lists.length}`);

	function openCreate() {
		newName = '';
		showCreate = true;
	}

	function closeCreate() {
		showCreate = false;
	}

	function create() {
		const name = newName.trim();
		if (!name) return;
		lastCreated = name;
		onCreate?.(name);
		newName = '';
		showCreate = false;
	}

	// Focus the name field as the modal opens.
	$effect(() => {
		if (showCreate && createInputEl) createInputEl.focus();
	});

	function rename(id: string, name: string) {
		lastRenamed = name;
		onRename?.(id, name);
	}

	function remove(id: string) {
		lastDeleted = id;
		onDelete?.(id);
	}
</script>

<section
	class="lists"
	data-verify-unit="lists-index"
	data-verify-count={visible.length}
	data-verify-total={lists.length}
	data-verify-empty={visible.length === 0 ? 'true' : 'false'}
	data-verify-default-first={visible[0]?.is_default ? 'true' : 'false'}
	data-verify-query={query}
	data-verify-first={visible[0]?.name ?? ''}
	data-verify-created={lastCreated}
	data-verify-renamed={lastRenamed}
	data-verify-deleted={lastDeleted}
	data-verify-queue-count={queueCount}
>
	<header class="head">
		<h1 class="display">Lists</h1>
	</header>

	<div class="controls">
		<div class="search">
			<input
				type="search"
				class="search-input"
				placeholder="Search lists…"
				aria-label="Search lists"
				value={search}
				oninput={(e) => (search = e.currentTarget.value)}
			/>
			{#if search}
				<button class="clear" aria-label="Clear search" onclick={() => (search = '')}>×</button>
			{/if}
		</div>

		<button class="new-list-btn" type="button" onclick={openCreate}>New list</button>

		<p class="count mono">{countLabel} {lists.length === 1 ? 'list' : 'lists'}</p>
	</div>

	{#if visible.length === 0}
		<p class="empty">
			{#if lists.length === 0}No lists yet.{:else}No lists match “{search.trim()}”.{/if}
		</p>
	{:else}
		<ul class="grid">
			{#if !query}
				<!-- The queue holds books, not recipes: a distinct clay-accented card, pinned
				     ahead of every list (search filters lists by name, so it steps aside). -->
				<li class="cell">
					<a class="queue-card" href="/lists/reading-queue" aria-label="Open the reading queue">
						<span class="queue-label mono">Up next</span>
						<span class="queue-name">Reading queue</span>
						<span class="queue-count mono">{queueCount} {queueCount === 1 ? 'book' : 'books'}</span>
					</a>
				</li>
			{/if}
			{#each visible as list, i (list.id)}
				<li class="cell" style={`animation-delay: ${Math.min(i * 30, 600)}ms`}>
					<ListCard
						id={list.id}
						name={list.name}
						isDefault={list.is_default}
						recipeCount={list.recipe_count}
						onRename={(name) => rename(list.id, name)}
						onDelete={() => remove(list.id)}
					/>
				</li>
			{/each}
		</ul>
	{/if}

	{#if showCreate}
		<!-- Full-bleed dismiss target behind the dialog: a real button so it's keyboard
		     operable and named (no static-element a11y violation). -->
		<button class="modal-scrim" type="button" aria-label="Cancel" onclick={closeCreate}></button>
		<div class="modal" role="dialog" aria-modal="true" aria-labelledby="new-list-title">
			<h2 id="new-list-title" class="modal-title">New list</h2>
			<input
				bind:this={createInputEl}
				class="modal-input"
				type="text"
				placeholder="List name…"
				aria-label="New list name"
				value={newName}
				oninput={(e) => (newName = e.currentTarget.value)}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.preventDefault();
						create();
					} else if (e.key === 'Escape') {
						closeCreate();
					}
				}}
			/>
			<div class="modal-actions">
				<button class="btn ghost" type="button" onclick={closeCreate}>Cancel</button>
				<button class="btn primary create-btn" type="button" onclick={create}>Create list</button>
			</div>
		</div>
	{/if}
</section>

<style>
	.lists {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}
	.head {
		margin-bottom: 1.75rem;
	}
	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3.2rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin: 0.2rem 0 0;
	}

	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem 1.5rem;
		margin-bottom: 2.5rem;
		padding-bottom: 1.25rem;
		border-bottom: var(--border);
	}
	.search {
		position: relative;
		display: flex;
		align-items: center;
		flex: 1 1 14rem;
		min-width: 0;
	}
	.search-input {
		width: 100%;
		font-family: var(--f-grotesk);
		font-size: 0.95rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.5rem 1.5rem 0.5rem 0;
		transition: border-color 0.18s var(--ease-out);
	}
	.search-input::placeholder {
		color: var(--faint);
	}
	.search-input:focus {
		border-bottom-color: var(--clay);
	}
	.clear {
		position: absolute;
		right: 0;
		display: flex;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--muted);
		font-size: 1.2rem;
		line-height: 1;
		padding: 0.15rem 0.25rem;
	}
	.clear:hover {
		color: var(--clay-deep);
	}

	.new-list-btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		color: var(--bg);
		background: var(--ink);
		border: 1px solid transparent;
		border-radius: 3px;
		padding: 0.5rem 0.95rem;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
		white-space: nowrap;
	}
	.new-list-btn:hover {
		background: var(--ink-deep);
	}

	/* Create-list modal */
	.modal-scrim {
		position: fixed;
		inset: 0;
		z-index: 60;
		border: none;
		padding: 0;
		cursor: default;
		background: rgba(28, 25, 23, 0.32);
		animation: fadeIn 0.15s var(--ease-out) both;
	}
	.modal {
		position: fixed;
		z-index: 61;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: min(26rem, calc(100vw - 2.5rem));
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 6px;
		padding: 1.6rem;
		box-shadow: 0 18px 50px rgba(0, 0, 0, 0.18);
		/* A dedicated keyframe — fadeUp's `transform: none` would clobber the
		   translate that centres the dialog. */
		animation: modalIn 0.2s var(--ease-out) both;
	}
	@keyframes modalIn {
		from {
			opacity: 0;
			transform: translate(-50%, -46%);
		}
		to {
			opacity: 1;
			transform: translate(-50%, -50%);
		}
	}
	.modal-title {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.6rem;
		font-weight: 400;
		color: var(--ink);
		margin: 0 0 1.1rem;
	}
	.modal-input {
		width: 100%;
		font-family: var(--f-grotesk);
		font-size: 1rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.5rem 0.1rem;
	}
	.modal-input:focus {
		outline: none;
		border-bottom-color: var(--clay);
	}
	.modal-input::placeholder {
		color: var(--faint);
	}
	.modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.6rem;
		margin-top: 1.5rem;
	}
	.btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		padding: 0.5rem 0.95rem;
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

	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	.count {
		margin: 0 0 0 auto;
		color: var(--muted);
	}

	.grid {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1.5rem var(--col-gap);
	}
	.cell {
		animation: fadeUp 0.6s var(--ease-out) both;
	}

	/* The queue card: books, not recipes — clay ground and ivory type so it reads as
	   its own thing, pinned ahead of the lists. */
	.queue-card {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 1rem;
		height: 100%;
		min-height: 8rem;
		padding: 1.25rem;
		background: var(--clay);
		border: 1px solid var(--clay);
		border-radius: 4px;
		text-decoration: none;
		transition: background 0.18s var(--ease-out);
	}
	.queue-card:hover {
		background: var(--clay-deep);
	}
	.queue-label {
		font-size: 0.68rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: rgba(255, 252, 245, 0.75);
	}
	.queue-name {
		font-family: var(--f-serif);
		font-size: 1.3rem;
		line-height: 1.2;
		color: #fffcf5;
	}
	.queue-count {
		font-size: 0.72rem;
		letter-spacing: 0.04em;
		color: rgba(255, 252, 245, 0.75);
	}

	/* Mobile: the queue card joins the hairline-row treatment of the list cards. */
	@media (max-width: 560px) {
		.queue-card {
			height: auto;
			min-height: 0;
			flex-direction: row;
			align-items: baseline;
			gap: 0.75rem;
			padding: 0.85rem 0.6rem;
			border-radius: 3px;
		}
		.queue-label {
			display: none;
		}
		.queue-name {
			font-size: 1.1rem;
			flex: 1;
		}
		.queue-count {
			white-space: nowrap;
		}
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		padding: 2rem 0;
		margin: 0;
	}

	@media (max-width: 1280px) {
		.grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}
	@media (max-width: 760px) {
		.lists {
			padding: var(--page-pt) var(--page-h) 3rem;
		}
		.count {
			margin-left: 0;
		}
		.grid {
			grid-template-columns: 1fr;
		}
	}
	/* Mobile: a continuous hairline list of compact rows (ListCard reshapes each
	   card into a row at the same breakpoint). */
	@media (max-width: 560px) {
		.grid {
			gap: 0;
			border-top: var(--border);
		}
	}
</style>
