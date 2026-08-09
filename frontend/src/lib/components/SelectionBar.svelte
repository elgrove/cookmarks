<script module lang="ts">
	import type { ListMembership } from '$lib/api/lists';

	export type SelectionBarProps = {
		/** Selected rows. */
		count: number;
		/** Rows on the page — the select-all target. */
		total: number;
		allSelected: boolean;
		/** Lists for the add panel. The bar adds rather than toggles, so `contains`
		 *  is ignored and the ticks are suppressed. */
		lists: ListMembership[];
		phase?: 'loading' | 'ready' | 'error';
		busy?: string | null;
		onSelectAll?: () => void;
		onClear?: () => void;
		onAdd?: (listId: string) => void;
		onCreate?: (name: string) => void;
		/** Rendered only when supplied — the list-detail bulk remove. */
		onRemove?: () => void;
		removeLabel?: string;
	};
</script>

<script lang="ts">
	import ListPanelBody from './ListPanelBody.svelte';

	let {
		count,
		total,
		allSelected,
		lists,
		phase = 'ready',
		busy = null,
		onSelectAll,
		onClear,
		onAdd,
		onCreate,
		onRemove,
		removeLabel
	}: SelectionBarProps = $props();

	let open = $state(false);
	// Echo the last interactions so the harness can verify wiring (cf. ListPicker).
	let lastAdded = $state('');
	let lastCreated = $state('');
	let removed = $state(false);
	let cleared = $state(false);

	// The bar adds, never removes — membership ticks are suppressed.
	let addable = $derived(lists.map((l) => ({ ...l, contains: false })));

	function add(list: ListMembership) {
		lastAdded = list.name;
		onAdd?.(list.id);
	}

	function create(name: string) {
		lastCreated = name;
		onCreate?.(name);
	}

	function clear() {
		cleared = true;
		open = false;
		onClear?.();
	}

	function remove() {
		removed = true;
		onRemove?.();
	}

	let barEl = $state<HTMLElement>();

	// While the add panel is open, a click anywhere outside the bar dismisses it.
	$effect(() => {
		if (!open) return;
		const onPointerDown = (e: Event) => {
			if (barEl && !barEl.contains(e.target as Node)) open = false;
		};
		document.addEventListener('pointerdown', onPointerDown, true);
		return () => document.removeEventListener('pointerdown', onPointerDown, true);
	});
</script>

<div
	class="bar"
	bind:this={barEl}
	data-verify-unit="selection-bar"
	data-verify-count={count}
	data-verify-total={total}
	data-verify-all={allSelected ? 'true' : 'false'}
	data-verify-open={open ? 'true' : 'false'}
	data-verify-added={lastAdded}
	data-verify-created={lastCreated}
	data-verify-removed={removed ? 'true' : 'false'}
	data-verify-cleared={cleared ? 'true' : 'false'}
>
	<p class="status mono" aria-live="polite">{count} selected</p>

	<div class="actions">
		<button
			class="select-all"
			type="button"
			disabled={allSelected || total === 0}
			onclick={() => onSelectAll?.()}
		>
			Select all {total}
		</button>
		<button class="clear-sel" type="button" disabled={count === 0} onclick={clear}>Clear</button>

		<div class="addwrap">
			<button
				class="add-btn"
				type="button"
				aria-expanded={open}
				disabled={count === 0}
				onclick={() => (open = !open)}
			>
				Add to list <span aria-hidden="true">▾</span>
			</button>
			{#if open}
				<div class="panel" role="group" aria-label="Add selection to a list">
					<ListPanelBody lists={addable} {phase} {busy} onToggle={add} onCreate={create} />
				</div>
			{/if}
		</div>

		{#if onRemove}
			<button class="bulk-remove" type="button" disabled={count === 0} onclick={remove}>
				{removeLabel ?? 'Remove from list'}
			</button>
		{/if}
	</div>
</div>

<style>
	.bar {
		position: sticky;
		z-index: 30;
		top: 0.75rem;
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 4px;
		padding: 0.55rem 0.9rem;
		margin-bottom: 1rem;
		box-shadow: 0 4px 18px rgba(0, 0, 0, 0.07);
	}

	.status {
		font-size: 0.78rem;
		letter-spacing: 0.04em;
		color: var(--ink);
		margin: 0;
		min-width: 6.5rem;
	}

	.actions {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-wrap: wrap;
	}

	.select-all,
	.clear-sel,
	.add-btn,
	.bulk-remove {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.8rem;
		border-radius: 3px;
		padding: 0.4rem 0.75rem;
		cursor: pointer;
		transition:
			border-color 0.16s var(--ease-out),
			color 0.16s var(--ease-out),
			background 0.16s var(--ease-out);
	}

	.select-all,
	.clear-sel {
		color: var(--ink);
		background: none;
		border: var(--border);
	}
	.select-all:hover:not(:disabled),
	.clear-sel:hover:not(:disabled) {
		border-color: var(--clay);
	}

	.add-btn {
		color: var(--bg);
		background: var(--ink);
		border: 1px solid var(--ink);
	}
	.add-btn:hover:not(:disabled) {
		background: var(--ink-deep);
	}

	.bulk-remove {
		color: #b3402a;
		background: none;
		border: 1px solid #b3402a;
	}
	.bulk-remove:hover:not(:disabled) {
		color: var(--bg);
		background: #b3402a;
	}

	.select-all:disabled,
	.clear-sel:disabled,
	.add-btn:disabled,
	.bulk-remove:disabled {
		opacity: 0.45;
		cursor: default;
	}

	.addwrap {
		position: relative;
	}

	.panel {
		position: absolute;
		z-index: 31;
		top: calc(100% + 0.4rem);
		left: 0;
		min-width: 15rem;
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 4px;
		padding: 0.5rem;
		box-shadow: 0 8px 28px rgba(0, 0, 0, 0.1);
	}

	@media (max-width: 760px) {
		/* The bar pins to the bottom edge on mobile, so the panel opens upward. */
		.bar {
			position: sticky;
			top: auto;
			bottom: 0.75rem;
		}
		.panel {
			top: auto;
			bottom: calc(100% + 0.4rem);
		}
	}
</style>
