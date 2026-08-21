<script module lang="ts">
	import type { ListMembership } from '$lib/api/lists';

	export type ListPickerProps = {
		/** Every list paired with whether this recipe is in it (Favourites first). */
		lists: ListMembership[];
		/** Render the panel open from the start (the trigger still toggles it). */
		open?: boolean;
		/** Called with the list and its *current* membership when a row is clicked. */
		onToggle?: (listId: string, contains: boolean) => void | Promise<void>;
		onCreate?: (name: string) => void | Promise<void>;
	};
</script>

<script lang="ts">
	import { untrack } from 'svelte';
	import ListPanelBody from './ListPanelBody.svelte';

	let { lists, open = false, onToggle, onCreate }: ListPickerProps = $props();

	// Seed the disclosure from the `open` prop once; the trigger owns it thereafter.
	let isOpen = $state(untrack(() => open));
	// Echo the last interaction so the harness can verify wiring without the parent
	// having to feed a mutated `lists` prop back in.
	let lastToggled = $state('');
	let lastCreated = $state('');

	let members = $derived(
		lists
			.filter((l) => l.contains)
			.map((l) => l.name)
			.join('|')
	);

	function dismiss() {
		isOpen = false;
		triggerEl?.focus();
	}

	async function toggle(list: ListMembership) {
		lastToggled = list.name;
		try {
			await onToggle?.(list.id, list.contains);
			dismiss();
		} catch (e) {
			console.error('list toggle failed', e);
		}
	}

	async function create(name: string) {
		lastCreated = name;
		try {
			await onCreate?.(name);
			dismiss();
		} catch (e) {
			console.error('list create failed', e);
		}
	}

	let pickerEl = $state<HTMLElement>();
	let triggerEl = $state<HTMLButtonElement>();

	// While open, a click anywhere outside the picker dismisses it. Clicks inside
	// (the trigger, the list toggles, the create field) are left to their own
	// handlers. The listener is attached after the opening click has finished, so
	// it never catches the click that opened the panel.
	$effect(() => {
		if (!isOpen) return;
		const onPointerDown = (e: Event) => {
			if (pickerEl && !pickerEl.contains(e.target as Node)) isOpen = false;
		};
		document.addEventListener('pointerdown', onPointerDown, true);
		return () => document.removeEventListener('pointerdown', onPointerDown, true);
	});
</script>

<div
	class="picker"
	bind:this={pickerEl}
	data-verify-unit="add-to-list"
	data-verify-open={isOpen ? 'true' : 'false'}
	data-verify-lists={lists.length}
	data-verify-members={members}
	data-verify-default-first={lists[0]?.is_default ? 'true' : 'false'}
	data-verify-toggled={lastToggled}
	data-verify-created={lastCreated}
>
	<button
		class="trigger"
		type="button"
		bind:this={triggerEl}
		aria-expanded={isOpen}
		onclick={() => (isOpen = !isOpen)}
	>
		Add to list <span class="ar" aria-hidden="true">›</span>
	</button>

	{#if isOpen}
		<div class="panel" role="group" aria-label="Add to a list">
			<ListPanelBody {lists} onToggle={toggle} onCreate={create} />
		</div>
	{/if}
</div>

<style>
	.picker {
		position: relative;
		display: inline-block;
	}
	.trigger {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		width: 100%;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		padding: 0.7rem 1rem;
		border-radius: 3px;
		background: var(--ink);
		color: var(--bg);
		border: 1px solid transparent;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
	}
	.trigger:hover {
		background: var(--ink-deep);
	}
	.trigger .ar {
		color: var(--bg);
		font-weight: 400;
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
</style>
