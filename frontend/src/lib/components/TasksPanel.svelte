<script module lang="ts">
	import type { TaskRunAck } from '$lib/api/tasks';

	export type TasksPanelProps = {
		/** Injected by the admin route (wired to POST /api/tasks/book-keywords); awaited
		 *  to drive running → done, or → error if it rejects. Kept network-free for the
		 *  verifiable unit, à la ExtractButton. */
		onRun?: (opts: { regenerate: boolean }) => Promise<TaskRunAck | void>;
	};

	type State = 'idle' | 'running' | 'done' | 'error';
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';

	let { onRun }: TasksPanelProps = $props();

	// Named runState, not `state`: a local `state` collides with the $state rune and
	// makes svelte2tsx read the runes as `any` (see MY-10/MY-12 notes).
	let runState = $state<State>('idle');
	let regenerate = $state(false);
	// The book count from the last successful queue; null until one runs (or on error).
	let queued = $state<number | null>(null);
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function run() {
		if (runState === 'running') return;
		clearTimeout(timer);
		runState = 'running';
		try {
			const ack = await onRun?.({ regenerate });
			queued = ack && typeof ack.queued === 'number' ? ack.queued : null;
			runState = 'done';
			// Fire-and-forget: there's no live view, so settle back to idle after a beat.
			timer = setTimeout(() => (runState = 'idle'), 3000);
		} catch {
			runState = 'error';
			queued = null;
			timer = setTimeout(() => (runState = 'idle'), 4000);
		}
	}

	onDestroy(() => clearTimeout(timer));

	let runLabel = $derived(
		runState === 'running'
			? 'Queuing…'
			: runState === 'done'
				? 'Queued ✓'
				: runState === 'error'
					? "Couldn't queue"
					: 'Run'
	);

	// A human note under the task after it runs: how many books were queued, or why not.
	let note = $derived(
		runState === 'done'
			? queued && queued > 0
				? `Queued ${queued} book${queued === 1 ? '' : 's'} for tagging — they'll update shortly.`
				: 'Nothing to tag: every extracted book already has keywords.'
			: runState === 'error'
				? 'The task could not be queued. Try again.'
				: ''
	);
</script>

<section
	class="tasks"
	data-verify-unit="tasks-panel"
	data-verify-state={runState}
	data-verify-regenerate={regenerate ? 'true' : 'false'}
	data-verify-queued={queued === null ? '' : String(queued)}
>
	<article class="task">
		<div class="copy">
			<h2 class="name">Generate book keywords</h2>
			<p class="desc">
				AI-tag every cookbook with book-level keywords — cuisine, theme and style — inferred from its
				recipes. New books are tagged automatically when extracted; run this to fill in the rest.
			</p>
			<label class="regen">
				<input
					type="checkbox"
					class="regen-check"
					aria-label="Regenerate keywords for books that already have them"
					checked={regenerate}
					onchange={(e) => (regenerate = e.currentTarget.checked)}
				/>
				<span class="regen-text"
					>Regenerate all <em>— re-tag books that already have keywords</em></span
				>
			</label>
		</div>

		<div class="action">
			<button
				class="run"
				class:done={runState === 'done'}
				class:error={runState === 'error'}
				type="button"
				aria-busy={runState === 'running'}
				disabled={runState === 'running'}
				onclick={run}
			>
				{runLabel}
			</button>
		</div>
	</article>

	{#if note}
		<p class="note" class:err={runState === 'error'} role="status">{note}</p>
	{/if}
</section>

<style>
	.tasks {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.task {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 2rem;
		padding: 1.5rem 0;
		border-top: var(--border-strong);
		border-bottom: var(--border);
	}

	.copy {
		min-width: 0;
		max-width: 42rem;
	}

	.name {
		font-family: var(--f-serif);
		font-weight: 600;
		font-size: 1.3rem;
		margin: 0;
	}

	.desc {
		font-family: var(--f-grotesk);
		font-size: 0.92rem;
		line-height: 1.6;
		color: var(--muted);
		margin: 0.5rem 0 0;
	}

	.regen {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		margin-top: 1rem;
		cursor: pointer;
		user-select: none;
	}

	.regen-check {
		appearance: none;
		width: 1rem;
		height: 1rem;
		margin: 0;
		flex: none;
		border: 1px solid var(--line-strong);
		border-radius: 3px;
		background-color: var(--bg);
		cursor: pointer;
		transition:
			border-color 0.18s var(--ease-out),
			background-color 0.18s var(--ease-out);
	}
	.regen-check:checked {
		border-color: var(--clay);
		background-color: var(--clay);
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='8' viewBox='0 0 10 8'%3E%3Cpath d='M1 4l3 3 5-6' fill='none' stroke='%23faf9f5' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: center;
	}
	.regen-check:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: 2px;
	}

	.regen-text {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--ink);
	}
	.regen-text em {
		font-style: normal;
		color: var(--muted);
	}

	.action {
		flex: none;
	}

	.run {
		min-width: 8.5rem;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		padding: 0.6rem 1.2rem;
		border-radius: 3px;
		background: var(--ink);
		color: var(--bg);
		border: 1px solid var(--ink);
		cursor: pointer;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.run:hover:not(:disabled) {
		background: var(--clay-deep);
		border-color: var(--clay-deep);
	}
	.run:disabled {
		cursor: default;
		background: transparent;
		color: var(--muted);
		border-color: var(--line-strong);
	}
	.run.done {
		background: var(--clay);
		border-color: var(--clay);
	}
	.run.error {
		background: transparent;
		color: var(--clay-deep);
		border-color: var(--clay-deep);
	}

	.note {
		font-family: var(--f-mono);
		font-size: 0.74rem;
		letter-spacing: 0.02em;
		color: var(--muted);
		margin: 0;
	}
	.note.err {
		color: var(--clay-deep);
	}

	@media (max-width: 560px) {
		.task {
			flex-direction: column;
			gap: 1.1rem;
		}
		.run {
			width: 100%;
		}
	}
</style>
