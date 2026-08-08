<script module lang="ts">
	import {
		addRecipeToList,
		createList,
		fetchRecipeLists,
		removeRecipeFromList,
		type ListMembership
	} from '$lib/api/lists';

	/** A rectangle in app-viewport coordinates (the trigger's, iframe offset already applied). */
	export type PanelAnchor = { x: number; y: number; w: number; h: number };

	/** The list endpoints the panel talks to — injectable so the harness can stub them. */
	export type PanelApi = {
		fetchRecipeLists: (recipeId: string) => Promise<ListMembership[]>;
		addRecipeToList: (listId: string, recipeId: string) => Promise<void>;
		removeRecipeFromList: (listId: string, recipeId: string) => Promise<void>;
		createList: (name: string) => Promise<{ id: string; name: string; is_default: boolean }>;
	};

	export type ReaderRecipePanelProps = {
		recipeId: string;
		recipeName: string;
		anchor: PanelAnchor;
		onClose: () => void;
		/** Fired when the default (Favourites) row is toggled, so the in-book star stays in sync. */
		onFavouriteChange?: (fav: boolean) => void;
		api?: PanelApi;
	};
</script>

<script lang="ts">
	import { onMount } from 'svelte';

	let {
		recipeId,
		recipeName,
		anchor,
		onClose,
		onFavouriteChange,
		api = { fetchRecipeLists, addRecipeToList, removeRecipeFromList, createList }
	}: ReaderRecipePanelProps = $props();

	let lists = $state<ListMembership[]>([]);
	let phase = $state<'loading' | 'ready' | 'error'>('loading');
	let newName = $state('');
	let busy = $state<string | null>(null);
	// Echo the last interactions so the harness can verify wiring (cf. ListPicker).
	let lastToggled = $state('');
	let lastCreated = $state('');
	let lastFavChange = $state('');

	onMount(async () => {
		try {
			lists = await api.fetchRecipeLists(recipeId);
			phase = 'ready';
		} catch (e) {
			console.error('could not load lists', e);
			phase = 'error';
		}
	});

	let members = $derived(
		lists
			.filter((l) => l.contains)
			.map((l) => l.name)
			.join('|')
	);

	async function toggle(list: ListMembership) {
		if (busy) return;
		busy = list.id;
		try {
			if (list.contains) await api.removeRecipeFromList(list.id, recipeId);
			else await api.addRecipeToList(list.id, recipeId);
			list.contains = !list.contains;
			lastToggled = list.name;
			if (list.is_default) {
				lastFavChange = String(list.contains);
				onFavouriteChange?.(list.contains);
			}
		} catch (e) {
			console.error('list toggle failed', e);
		} finally {
			busy = null;
		}
	}

	async function create() {
		const name = newName.trim();
		if (!name || busy) return;
		busy = 'create';
		try {
			const created = await api.createList(name);
			await api.addRecipeToList(created.id, recipeId);
			lists = [
				...lists,
				{ id: created.id, name: created.name, is_default: created.is_default, contains: true }
			];
			lastCreated = created.name;
			newName = '';
		} catch (e) {
			console.error('list create failed', e);
		} finally {
			busy = null;
		}
	}

	const PANEL_W = 270;
	let style = $derived.by(() => {
		const x = Math.round(Math.min(Math.max(8, anchor.x - 40), window.innerWidth - PANEL_W - 8));
		const y = Math.round(Math.min(anchor.y + anchor.h + 8, window.innerHeight - 280));
		return `left:${x}px; top:${y}px; width:${PANEL_W}px;`;
	});
</script>

<button class="scrim" aria-label="Close" onclick={onClose}></button>

<div
	class="panel"
	{style}
	role="dialog"
	aria-label={`Save ${recipeName} to a list`}
	data-verify-unit="reader-recipe-panel"
	data-verify-phase={phase}
	data-verify-lists={lists.length}
	data-verify-members={members}
	data-verify-default-first={lists[0]?.is_default ? 'true' : 'false'}
	data-verify-toggled={lastToggled}
	data-verify-created={lastCreated}
	data-verify-fav-change={lastFavChange}
>
	<header class="head">
		<span class="name">{recipeName}</span>
		<button class="close" type="button" aria-label="Close" onclick={onClose}>×</button>
	</header>

	{#if phase === 'loading'}
		<p class="note">Loading lists…</p>
	{:else if phase === 'error'}
		<p class="note">Couldn’t load your lists.</p>
	{:else}
		<ul class="lists">
			{#each lists as list (list.id)}
				<li>
					<button
						class="row"
						class:on={list.contains}
						type="button"
						aria-pressed={list.contains}
						disabled={busy === list.id}
						onclick={() => toggle(list)}
					>
						<span class="tick" aria-hidden="true">{list.contains ? '✓' : ''}</span>
						<span class="rname">{list.name}</span>
						{#if list.is_default}<span class="star" aria-hidden="true">★</span>{/if}
					</button>
				</li>
			{/each}
		</ul>

		<div class="create">
			<input
				class="create-input"
				type="text"
				placeholder="New list…"
				aria-label="New list name"
				bind:value={newName}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.preventDefault();
						create();
					}
				}}
			/>
			<button class="create-btn" type="button" disabled={busy === 'create'} onclick={create}
				>Create</button
			>
		</div>
	{/if}

	<a class="view" href={`/recipes/${recipeId}`}>View recipe <span aria-hidden="true">→</span></a>
</div>

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 40;
		background: transparent;
		border: none;
		padding: 0;
		cursor: default;
	}

	.panel {
		position: fixed;
		z-index: 41;
		display: flex;
		flex-direction: column;
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 4px;
		padding: 0.6rem 0.7rem 0.7rem;
		max-height: 55dvh;
		overflow-y: auto;
		box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
	}

	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.8rem;
		margin-bottom: 0.4rem;
	}
	.name {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1rem;
		color: var(--ink);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.close {
		font-family: var(--f-grotesk);
		font-size: 1.1rem;
		line-height: 1;
		color: var(--muted);
		background: none;
		border: none;
		padding: 0.1rem 0.3rem;
		cursor: pointer;
	}
	.close:hover {
		color: var(--ink);
	}

	.note {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--muted);
		margin: 0.4rem 0;
	}

	.lists {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		width: 100%;
		text-align: left;
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background: none;
		border: none;
		border-radius: 3px;
		padding: 0.5rem 0.6rem;
		cursor: pointer;
		transition: background 0.15s var(--ease-out);
	}
	.row:hover {
		background: var(--bg-warm);
	}
	.row[disabled] {
		opacity: 0.6;
	}
	.row .tick {
		width: 1rem;
		color: var(--clay);
		font-size: 0.85rem;
	}
	.row.on .rname {
		color: var(--clay-deep);
	}
	.row .rname {
		flex: 1;
	}
	.row .star {
		color: var(--clay);
		font-size: 0.8rem;
	}

	.create {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: var(--border);
	}
	.create-input {
		flex: 1;
		min-width: 0;
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.35rem 0.2rem;
	}
	.create-input:focus {
		outline: none;
		border-bottom-color: var(--clay);
	}
	.create-input::placeholder {
		color: var(--faint);
	}
	.create-btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.8rem;
		color: var(--ink);
		background: none;
		border: 1px solid var(--line-strong);
		border-radius: 3px;
		padding: 0.35rem 0.7rem;
		cursor: pointer;
		transition: border-color 0.18s var(--ease-out);
	}
	.create-btn:hover {
		border-color: var(--clay);
		color: var(--clay-deep);
	}

	.view {
		margin-top: 0.6rem;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.82rem;
		color: var(--clay-deep);
		text-decoration: none;
		align-self: flex-start;
	}
	.view:hover {
		text-decoration: underline;
	}
</style>
