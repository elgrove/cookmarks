<script module lang="ts">
	import type { ListMembership } from '$lib/api/lists';

	export type ListPickerProps = {
		/** Every list paired with whether this recipe is in it (Favourites first). */
		lists: ListMembership[];
		/** Render the panel open from the start (the trigger still toggles it). */
		open?: boolean;
		/** Called with the list and its *current* membership when a row is clicked. */
		onToggle?: (listId: string, contains: boolean) => void;
		onCreate?: (name: string) => void;
	};
</script>

<script lang="ts">
	import { untrack } from 'svelte';

	let { lists, open = false, onToggle, onCreate }: ListPickerProps = $props();

	// Seed the disclosure from the `open` prop once; the trigger owns it thereafter.
	let isOpen = $state(untrack(() => open));
	let newName = $state('');
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

	function toggle(list: ListMembership) {
		lastToggled = list.name;
		onToggle?.(list.id, list.contains);
	}

	function create() {
		const name = newName.trim();
		if (!name) return;
		lastCreated = name;
		onCreate?.(name);
		newName = '';
	}

	let pickerEl = $state<HTMLElement>();

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
		aria-expanded={isOpen}
		onclick={() => (isOpen = !isOpen)}
	>
		Add to list <span class="ar" aria-hidden="true">›</span>
	</button>

	{#if isOpen}
		<div class="panel" role="group" aria-label="Add to a list">
			<ul class="lists">
				{#each lists as list (list.id)}
					<li>
						<button
							class="list-toggle"
							class:on={list.contains}
							type="button"
							aria-pressed={list.contains}
							onclick={() => toggle(list)}
						>
							<span class="tick" aria-hidden="true">{list.contains ? '✓' : ''}</span>
							<span class="name">{list.name}</span>
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
					value={newName}
					oninput={(e) => (newName = e.currentTarget.value)}
					onkeydown={(e) => {
						if (e.key === 'Enter') {
							e.preventDefault();
							create();
						}
					}}
				/>
				<button class="create-btn" type="button" onclick={create}>Create</button>
			</div>
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
	.list-toggle .tick {
		width: 1rem;
		color: var(--clay);
		font-size: 0.85rem;
	}
	.list-toggle.on .name {
		color: var(--clay-deep);
	}
	.list-toggle .name {
		flex: 1;
	}
	.list-toggle .star {
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
</style>
