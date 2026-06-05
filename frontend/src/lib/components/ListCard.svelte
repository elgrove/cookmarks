<script module lang="ts">
	export type ListCardData = {
		id: string;
		name: string;
		isDefault: boolean;
		recipeCount: number;
	};
</script>

<script lang="ts">
	type Props = ListCardData & {
		onRename?: (name: string) => void;
		onDelete?: () => void;
	};

	let { id, name, isDefault, recipeCount, onRename, onDelete }: Props = $props();

	let mode = $state<'view' | 'rename' | 'confirm'>('view');
	let editName = $state('');

	function startRename() {
		editName = name;
		mode = 'rename';
	}

	function saveRename() {
		const next = editName.trim();
		if (next && next !== name) onRename?.(next);
		mode = 'view';
	}

	function confirmDelete() {
		onDelete?.();
		mode = 'view';
	}
</script>

<article class="card" class:default={isDefault}>
	{#if mode === 'rename'}
		<div class="rename">
			<input
				class="rename-input"
				type="text"
				aria-label={`Rename list ${name}`}
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
				<button class="act save rename-save" type="button" onclick={saveRename}>Save</button>
				<button class="act" type="button" onclick={() => (mode = 'view')}>Cancel</button>
			</div>
		</div>
	{:else if mode === 'confirm'}
		<div class="confirm">
			<p class="prompt">Delete “{name}”?</p>
			<div class="actions">
				<button class="act danger confirm-delete" type="button" onclick={confirmDelete}>
					Delete
				</button>
				<button class="act" type="button" onclick={() => (mode = 'view')}>Cancel</button>
			</div>
		</div>
	{:else}
		<a class="link" href={`/lists/${id}`} aria-label={`Open list ${name}`}>
			<span class="title">
				{#if isDefault}<span class="star" aria-hidden="true">★</span>{/if}<span class="name"
					>{name}</span
				>
			</span>
			<span class="count mono">{recipeCount} {recipeCount === 1 ? 'recipe' : 'recipes'}</span>
		</a>
		{#if !isDefault}
			<div class="footer">
				<button class="act rename-btn" type="button" onclick={startRename}>Rename</button>
				<button class="act delete-btn" type="button" onclick={() => (mode = 'confirm')}>
					Delete
				</button>
			</div>
		{/if}
	{/if}
</article>

<style>
	.card {
		/* Anchor for the stretched-link overlay so the whole surface navigates. */
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 1rem;
		/* Fill the grid cell so every card in a row shares one height — the default
		   Favourites card is no taller than the rest. */
		height: 100%;
		min-height: 8rem;
		padding: 1.25rem;
		background: var(--bg-warm);
		border: var(--border);
		border-radius: 4px;
		transition: border-color 0.18s var(--ease-out);
	}
	.card:hover {
		border-color: var(--clay);
	}
	.card.default {
		border-color: var(--clay);
	}

	.link {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		text-decoration: none;
	}
	/* Stretched link: the anchor's ::after covers the whole card, so a click
	   anywhere on the surface navigates — without nesting the footer buttons
	   inside the <a> (which would be invalid HTML). */
	.link::after {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: 4px;
	}
	.title {
		display: flex;
		align-items: baseline;
		gap: 0.45rem;
		min-width: 0;
	}
	.star {
		flex: none;
		color: var(--clay);
		font-size: 0.9rem;
	}
	.name {
		font-family: var(--f-serif);
		font-size: 1.3rem;
		line-height: 1.2;
		color: var(--ink);
		transition: color 0.18s var(--ease-out);
	}
	.card:hover .name {
		color: var(--clay-deep);
	}
	.count {
		font-size: 0.72rem;
		letter-spacing: 0.04em;
		color: var(--muted);
	}

	.footer {
		display: flex;
		align-items: center;
		gap: 1rem;
		/* Sit above the stretched-link overlay so Rename / Delete stay clickable
		   and never trigger navigation. */
		position: relative;
		z-index: 1;
	}
	.act {
		font-family: var(--f-grotesk);
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--muted);
		background: none;
		border: none;
		border-bottom: 1px solid transparent;
		padding: 0;
		cursor: pointer;
		transition: color 0.18s var(--ease-out);
	}
	.act:hover {
		color: var(--clay-deep);
		border-bottom-color: var(--clay);
	}
	.act.danger:hover {
		color: #b3402a;
		border-bottom-color: #b3402a;
	}
	.act.save {
		color: var(--ink);
	}

	.rename,
	.confirm {
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
		height: 100%;
		justify-content: center;
	}
	.rename-input {
		font-family: var(--f-serif);
		font-size: 1.15rem;
		color: var(--ink);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--line-strong);
		padding: 0.3rem 0.1rem;
	}
	.rename-input:focus {
		outline: none;
		border-bottom-color: var(--clay);
	}
	.prompt {
		font-family: var(--f-serif);
		font-size: 1.05rem;
		color: var(--ink);
		margin: 0;
	}
	.actions {
		display: flex;
		gap: 1rem;
	}
</style>
