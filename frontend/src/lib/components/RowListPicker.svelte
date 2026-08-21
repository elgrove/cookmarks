<script module lang="ts">
	import {
		addRecipeToList,
		createList,
		fetchRecipeLists,
		removeRecipeFromList,
		type ListMembership,
		type ListPanelApi
	} from '$lib/api/lists';

	export type RowListPickerProps = {
		recipeId: string;
		recipeName: string;
		api?: ListPanelApi;
		/** Viewport height used for the flip decision — injectable for the harness
		 *  (jsdom rects are all zero). Defaults to window.innerHeight at open time. */
		viewport?: { h: number };
		/** Fired after a successful toggle, with the list and its *new* membership. */
		onMembershipChange?: (listId: string, contains: boolean) => void;
	};
</script>

<script lang="ts">
	import ListPanelBody from './ListPanelBody.svelte';

	let {
		recipeId,
		recipeName,
		api = { fetchRecipeLists, addRecipeToList, removeRecipeFromList, createList },
		viewport,
		onMembershipChange
	}: RowListPickerProps = $props();

	let open = $state(false);
	let placement = $state<'down' | 'up'>('down');
	let lists = $state<ListMembership[]>([]);
	let phase = $state<'loading' | 'ready' | 'error'>('loading');
	let busy = $state<string | null>(null);
	// Echo the last interactions so the harness can verify wiring (cf. ListPicker).
	let lastToggled = $state('');
	let lastCreated = $state('');
	// Memberships are lazy: fetched once, on the first open.
	let fetched = false;

	let members = $derived(
		lists
			.filter((l) => l.contains)
			.map((l) => l.name)
			.join('|')
	);

	let pickerEl = $state<HTMLElement>();
	let triggerEl = $state<HTMLButtonElement>();

	// Rough panel height for the flip decision — enough for a handful of rows plus
	// the create field. Only the above/below choice needs it, not exact fit.
	const PANEL_H = 320;

	function toggleOpen() {
		open = !open;
		if (!open) return;
		const vh = viewport?.h ?? window.innerHeight;
		const bottom = triggerEl?.getBoundingClientRect().bottom ?? 0;
		placement = bottom + PANEL_H > vh ? 'up' : 'down';
		if (!fetched) {
			fetched = true;
			void load();
		}
	}

	async function load() {
		try {
			lists = await api.fetchRecipeLists(recipeId);
			phase = 'ready';
		} catch (e) {
			console.error('could not load lists', e);
			phase = 'error';
			// Let the next open retry rather than pinning the error for the mount.
			fetched = false;
		}
	}

	function dismiss() {
		open = false;
		triggerEl?.focus();
	}

	async function toggle(list: ListMembership) {
		if (busy) return;
		busy = list.id;
		try {
			if (list.contains) await api.removeRecipeFromList(list.id, recipeId);
			else await api.addRecipeToList(list.id, recipeId);
			list.contains = !list.contains;
			lastToggled = list.name;
			onMembershipChange?.(list.id, list.contains);
			dismiss();
		} catch (e) {
			console.error('list toggle failed', e);
		} finally {
			busy = null;
		}
	}

	async function create(name: string) {
		if (busy) return;
		busy = 'create';
		try {
			const created = await api.createList(name);
			lastCreated = created.name;
			// The list now exists server-side either way — show it, unticked if the add failed,
			// so a retry is a toggle rather than a duplicate create.
			let contains = true;
			try {
				await api.addRecipeToList(created.id, recipeId);
			} catch (e) {
				console.error('could not add recipe to new list', e);
				contains = false;
			}
			lists = [
				...lists,
				{ id: created.id, name: created.name, is_default: created.is_default, contains }
			];
			if (contains) {
				onMembershipChange?.(created.id, true);
				dismiss();
			}
		} catch (e) {
			console.error('list create failed', e);
		} finally {
			busy = null;
		}
	}

	// While open, a click anywhere outside dismisses; Escape closes too.
	$effect(() => {
		if (!open) return;
		const onPointerDown = (e: Event) => {
			if (pickerEl && !pickerEl.contains(e.target as Node)) open = false;
		};
		document.addEventListener('pointerdown', onPointerDown, true);
		return () => document.removeEventListener('pointerdown', onPointerDown, true);
	});
</script>

<svelte:window
	onkeydown={(e) => {
		if (open && e.key === 'Escape') open = false;
	}}
/>

<div
	class="rowpicker"
	bind:this={pickerEl}
	data-verify-unit="row-list-picker"
	data-verify-open={open ? 'true' : 'false'}
	data-verify-phase={phase}
	data-verify-lists={lists.length}
	data-verify-members={members}
	data-verify-default-first={lists[0]?.is_default ? 'true' : 'false'}
	data-verify-toggled={lastToggled}
	data-verify-created={lastCreated}
	data-verify-placement={placement}
>
	<button
		class="add-trigger"
		type="button"
		bind:this={triggerEl}
		aria-label={`Add ${recipeName} to a list`}
		aria-expanded={open}
		onclick={toggleOpen}
	>
		<svg
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			aria-hidden="true"
		>
			<line x1="12" y1="5" x2="12" y2="19" />
			<line x1="5" y1="12" x2="19" y2="12" />
		</svg>
	</button>

	{#if open}
		<div class="panel" class:up={placement === 'up'} role="group" aria-label="Add to a list">
			<ListPanelBody {lists} {phase} {busy} onToggle={toggle} onCreate={create} />
		</div>
	{/if}
</div>

<style>
	.rowpicker {
		position: relative;
		display: inline-flex;
	}

	.add-trigger {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.55rem;
		height: 1.55rem;
		border-radius: 3px;
		color: var(--muted);
		background: none;
		border: var(--border);
		cursor: pointer;
		transition:
			color 0.16s var(--ease-out),
			border-color 0.16s var(--ease-out);
	}
	.add-trigger:hover,
	.add-trigger[aria-expanded='true'] {
		color: var(--clay-deep);
		border-color: var(--clay);
	}
	.add-trigger svg {
		display: block;
		width: 0.85rem;
		height: 0.85rem;
	}

	.panel {
		position: absolute;
		z-index: 20;
		top: calc(100% + 0.4rem);
		right: 0;
		min-width: 15rem;
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 4px;
		padding: 0.5rem;
		box-shadow: 0 8px 28px rgba(0, 0, 0, 0.1);
	}
	.panel.up {
		top: auto;
		bottom: calc(100% + 0.4rem);
	}
</style>
