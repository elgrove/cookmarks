<script module lang="ts">
	export type ExtractButtonProps = {
		/** How many recipes the book already has — switches the label to "Re-extract". */
		recipeCount?: number;
		/** Injected so the component stays network-free and verifiable in isolation;
		 *  the page wires this to the POST. Awaited to drive posting → queued. */
		onExtract?: () => Promise<void> | void;
	};

	type State = 'idle' | 'posting' | 'queued' | 'error';
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';

	let { recipeCount = 0, onExtract }: ExtractButtonProps = $props();

	let state = $state<State>('idle');
	let timer: ReturnType<typeof setTimeout> | undefined;

	let idleLabel = $derived(recipeCount > 0 ? 'Re-extract recipes' : 'Extract recipes');
	let label = $derived(
		state === 'posting'
			? 'Queuing…'
			: state === 'queued'
				? 'Queued'
				: state === 'error'
					? "Couldn't queue — try again"
					: idleLabel
	);

	async function extract() {
		if (state === 'posting') return;
		clearTimeout(timer);
		state = 'posting';
		try {
			await onExtract?.();
			state = 'queued';
			// Fire-and-forget: there's no live view, so settle back to idle after a beat.
			timer = setTimeout(() => (state = 'idle'), 2500);
		} catch {
			state = 'error';
			timer = setTimeout(() => (state = 'idle'), 4000);
		}
	}

	onDestroy(() => clearTimeout(timer));
</script>

<button
	class="extract"
	class:queued={state === 'queued'}
	class:error={state === 'error'}
	type="button"
	data-verify-unit="extract-button"
	data-verify-state={state}
	data-verify-recipe-count={recipeCount}
	aria-label={label}
	aria-busy={state === 'posting'}
	disabled={state === 'posting'}
	onclick={extract}
>
	<span class="text">{label}</span>
	<span class="mark" aria-hidden="true">
		{#if state === 'queued'}✓{:else if state === 'error'}↻{:else}›{/if}
	</span>
</button>

<style>
	.extract {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		padding: 0.7rem 1rem;
		border-radius: 3px;
		background: transparent;
		color: var(--accent-deep);
		border: 1px solid var(--accent);
		cursor: pointer;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.extract:hover:not(:disabled) {
		background: var(--accent);
		color: var(--bg);
	}
	.extract:disabled {
		cursor: default;
		color: var(--muted);
		border-color: var(--line-strong);
	}
	.extract.queued {
		background: var(--accent);
		color: var(--bg);
		border-color: var(--accent);
	}
	.extract.error {
		color: var(--accent-deep);
		border-color: var(--accent-deep);
	}
	.mark {
		font-weight: 400;
	}
</style>
