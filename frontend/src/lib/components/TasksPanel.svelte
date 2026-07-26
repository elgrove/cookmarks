<script module lang="ts">
	import type { TaskRunAck } from '$lib/api/tasks';

	export type TasksPanelProps = {
		/** Injected by the admin route (wired to POST /api/tasks/book-keywords); awaited
		 *  to drive running → done, or → error if it rejects. Kept network-free for the
		 *  verifiable unit, à la ExtractButton. */
		onRun?: (opts: { regenerate: boolean }) => Promise<TaskRunAck | void>;
		/** Wired to POST /api/tasks/dedup-keywords — the AI-assisted keyword merge. Same
		 *  fire-and-forget lifecycle as `onRun`, with no options. */
		onDedup?: () => Promise<TaskRunAck | void>;
		/** Wired to POST /api/tasks/calibre-sync — re-reads the Calibre library and
		 *  reconciles books. Same fire-and-forget lifecycle, with no options. */
		onSync?: () => Promise<TaskRunAck | void>;
	};

	type State = 'idle' | 'running' | 'done' | 'error';
	// One task's lifecycle. `state` is named so, not `state`, to avoid the $state rune
	// collision that makes svelte2tsx read runes as `any` (see MY-10/MY-12 notes); held
	// on an object so the two tasks share one run helper. `queued` is the unit count from
	// the last successful queue (books / keywords), null until one runs or on error.
	type Runner = { state: State; queued: number | null; timer?: ReturnType<typeof setTimeout> };
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';

	let { onRun, onDedup, onSync }: TasksPanelProps = $props();

	let book = $state<Runner>({ state: 'idle', queued: null });
	let dedup = $state<Runner>({ state: 'idle', queued: null });
	let calibre = $state<Runner>({ state: 'idle', queued: null });
	let regenerate = $state(false);

	// `run` may be absent (an unwired handler returns undefined), hence the widened
	// return — `await undefined` simply yields no ack and the note falls back.
	async function runTask(runner: Runner, run: () => Promise<TaskRunAck | void> | undefined) {
		if (runner.state === 'running') return;
		clearTimeout(runner.timer);
		runner.state = 'running';
		try {
			const ack = await run();
			runner.queued = ack && typeof ack.queued === 'number' ? ack.queued : null;
			runner.state = 'done';
			// Fire-and-forget: there's no live view, so settle back to idle after a beat.
			runner.timer = setTimeout(() => (runner.state = 'idle'), 3000);
		} catch {
			runner.state = 'error';
			runner.queued = null;
			runner.timer = setTimeout(() => (runner.state = 'idle'), 4000);
		}
	}

	onDestroy(() => {
		clearTimeout(book.timer);
		clearTimeout(dedup.timer);
		clearTimeout(calibre.timer);
	});

	function label(state: State): string {
		return state === 'running'
			? 'Queuing…'
			: state === 'done'
				? 'Queued ✓'
				: state === 'error'
					? "Couldn't queue"
					: 'Run';
	}

	const ERROR_NOTE = 'The task could not be queued. Try again.';

	// A human note under each task after it runs: how many units were queued, or why not.
	let bookNote = $derived(
		book.state === 'done'
			? book.queued && book.queued > 0
				? `Queued ${book.queued} book${book.queued === 1 ? '' : 's'} for tagging — they'll update shortly.`
				: 'Nothing to tag: every extracted book already has keywords.'
			: book.state === 'error'
				? ERROR_NOTE
				: ''
	);
	let dedupNote = $derived(
		dedup.state === 'done'
			? dedup.queued && dedup.queued > 0
				? `Analysing ${dedup.queued} keyword${dedup.queued === 1 ? '' : 's'} for merges — duplicates fold shortly.`
				: 'Nothing to deduplicate: the keyword vocabulary is empty.'
			: dedup.state === 'error'
				? ERROR_NOTE
				: ''
	);
	let calibreNote = $derived(
		calibre.state === 'done'
			? 'Syncing the Calibre library — new and changed books land shortly. See the result in Task Runs.'
			: calibre.state === 'error'
				? ERROR_NOTE
				: ''
	);
</script>

<section
	class="tasks"
	data-verify-unit="tasks-panel"
	data-verify-state={book.state}
	data-verify-regenerate={regenerate ? 'true' : 'false'}
	data-verify-queued={book.queued === null ? '' : String(book.queued)}
	data-verify-dedup-state={dedup.state}
	data-verify-dedup-queued={dedup.queued === null ? '' : String(dedup.queued)}
	data-verify-calibre-state={calibre.state}
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
				class:done={book.state === 'done'}
				class:error={book.state === 'error'}
				type="button"
				aria-busy={book.state === 'running'}
				disabled={book.state === 'running'}
				onclick={() => runTask(book, () => onRun?.({ regenerate }))}
			>
				{label(book.state)}
			</button>
		</div>
	</article>

	{#if bookNote}
		<p class="note" class:err={book.state === 'error'} role="status">{bookNote}</p>
	{/if}

	<article class="task">
		<div class="copy">
			<h2 class="name">Deduplicate keywords</h2>
			<p class="desc">
				Use AI to merge near-duplicate tags — "Veggie" into "Vegetarian", "Stir Fry" into "Stir-fry"
				— across every recipe and book, so search and filtering stay sharp. Merges apply
				automatically; there's no review step.
			</p>
		</div>

		<div class="action">
			<button
				class="run dedup-run"
				class:done={dedup.state === 'done'}
				class:error={dedup.state === 'error'}
				type="button"
				aria-busy={dedup.state === 'running'}
				disabled={dedup.state === 'running'}
				onclick={() => runTask(dedup, () => onDedup?.())}
			>
				{label(dedup.state)}
			</button>
		</div>
	</article>

	{#if dedupNote}
		<p class="note" class:err={dedup.state === 'error'} role="status">{dedupNote}</p>
	{/if}

	<article class="task">
		<div class="copy">
			<h2 class="name">Sync Calibre library</h2>
			<p class="desc">
				Re-read the Calibre library and reconcile it — add newly-tagged cookbooks, refresh changed
				metadata, flag books that have left the tag/format selection, and remove books deleted
				from the library along with their recipes. Recipes, favourites and lists are untouched
				for books that remain. The run's result (created, updated, orphaned, deleted) lands in
				Task Runs.
			</p>
		</div>

		<div class="action">
			<button
				class="run calibre-run"
				class:done={calibre.state === 'done'}
				class:error={calibre.state === 'error'}
				type="button"
				aria-busy={calibre.state === 'running'}
				disabled={calibre.state === 'running'}
				onclick={() => runTask(calibre, () => onSync?.())}
			>
				{label(calibre.state)}
			</button>
		</div>
	</article>

	{#if calibreNote}
		<p class="note" class:err={calibre.state === 'error'} role="status">{calibreNote}</p>
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
