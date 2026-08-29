<script module lang="ts">
	import type { ListMembership } from '$lib/api/lists';

	export type ListPanelBodyProps = {
		/** Every list paired with whether the recipe is in it (Favourites first). */
		lists: ListMembership[];
		phase?: 'loading' | 'ready' | 'error';
		/** Id of the list with an operation in flight ('create' for the create field). */
		busy?: string | null;
		showCreate?: boolean;
		/** Called with the list and its *current* membership when a row is clicked. */
		onToggle?: (list: ListMembership) => void;
		onCreate?: (name: string) => void;
	};
</script>

<script lang="ts">
	let {
		lists,
		phase = 'ready',
		busy = null,
		showCreate = true,
		onToggle,
		onCreate
	}: ListPanelBodyProps = $props();

	let newName = $state('');

	function create() {
		const name = newName.trim();
		if (!name) return;
		onCreate?.(name);
		newName = '';
	}
</script>

<div
	class="body"
	data-verify-unit="list-panel-body"
	data-verify-phase={phase}
	data-verify-lists={lists.length}
	data-verify-create={showCreate ? 'true' : 'false'}
	data-verify-busy={busy ?? ''}
>
	{#if phase === 'loading'}
		<p class="note">Loading lists…</p>
	{:else if phase === 'error'}
		<p class="note">Couldn’t load your lists.</p>
	{:else}
		<ul class="lists">
			{#each lists as list (list.id)}
				<li>
					<button
						class="list-toggle"
						class:on={list.contains}
						type="button"
						aria-pressed={list.contains}
						disabled={busy === list.id}
						onclick={() => onToggle?.(list)}
					>
						<span class="tick" aria-hidden="true">{list.contains ? '✓' : ''}</span>
						<span class="name">{list.name}</span>
						{#if list.is_default}<span class="star" aria-hidden="true">★</span>{/if}
					</button>
				</li>
			{/each}
		</ul>

		{#if showCreate}
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
	{/if}
</div>

<style>
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
	.list-toggle {
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
	.list-toggle:hover {
		background: var(--bg-warm);
	}
	.list-toggle[disabled] {
		opacity: 0.6;
	}
	.list-toggle .tick {
		width: 1rem;
		color: var(--accent);
		font-size: 0.85rem;
	}
	.list-toggle.on .name {
		color: var(--accent-deep);
	}
	.list-toggle .name {
		flex: 1;
	}
	.list-toggle .star {
		color: var(--accent);
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
		border-bottom-color: var(--accent);
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
		border-color: var(--accent);
		color: var(--accent-deep);
	}
</style>
