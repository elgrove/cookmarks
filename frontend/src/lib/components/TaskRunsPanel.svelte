<script module lang="ts">
	import type {
		TaskRun,
		TaskType,
		ExtractionDetail,
		BookKeywordsDetail,
		KeywordDedupDetail,
		CalibreSyncDetail,
		BookIngestDetail
	} from '$lib/api/task-runs';

	export type TaskRunsPanelProps = {
		/** Every task run, newest first (the server's order is preserved). Network-free
		 *  and verifiable in isolation; the admin route owns the fetch. */
		runs: TaskRun[];
	};

	type Filter = TaskType | 'all';

	const FILTERS: { id: Filter; label: string }[] = [
		{ id: 'all', label: 'All' },
		{ id: 'extraction', label: 'Extraction' },
		{ id: 'book_keywords', label: 'Keywords' },
		{ id: 'keyword_dedup', label: 'Dedup' },
		{ id: 'calibre_sync', label: 'Calibre' },
		{ id: 'book_ingest', label: 'Added books' }
	];

	const TYPE_LABELS: Record<TaskType, string> = {
		extraction: 'Extraction',
		book_keywords: 'Book keywords',
		keyword_dedup: 'Keyword dedup',
		calibre_sync: 'Calibre sync',
		book_ingest: 'Add book'
	};

	const rowDateFmt = new Intl.DateTimeFormat('en-GB', {
		day: 'numeric',
		month: 'short',
		year: 'numeric'
	});

	function rowDate(iso: string): string {
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? '—' : rowDateFmt.format(d);
	}

	function plural(n: number, one: string): string {
		return `${n} ${one}${n === 1 ? '' : 's'}`;
	}

	// A one-line outcome per run for the list row, read from its `detail` payload.
	function rowSummary(run: TaskRun): string {
		switch (run.task_type) {
			case 'extraction':
				return plural((run.detail as unknown as ExtractionDetail).recipes_found ?? 0, 'recipe');
			case 'book_keywords':
				return `${(run.detail as unknown as BookKeywordsDetail).books_tagged ?? 0} tagged`;
			case 'keyword_dedup':
				return plural((run.detail as unknown as KeywordDedupDetail).merges_applied ?? 0, 'merge');
			case 'calibre_sync': {
				const d = run.detail as unknown as CalibreSyncDetail;
				return `${d.created?.length ?? 0} new · ${d.updated?.length ?? 0} updated`;
			}
			case 'book_ingest':
				return (run.detail as unknown as BookIngestDetail).title || 'Add book';
		}
	}
</script>

<script lang="ts">
	import TaskStatusBadge from './TaskStatusBadge.svelte';
	import TaskRunDetail from './TaskRunDetail.svelte';
	import { cleanTitle } from '$lib/title';

	let { runs }: TaskRunsPanelProps = $props();

	let filter = $state<Filter>('all');
	let selectedId = $state<string | null>(null);

	let filtered = $derived(filter === 'all' ? runs : runs.filter((r) => r.task_type === filter));

	// Default to the newest run in the current filter; an explicit click overrides, and a
	// filter change that drops the selection falls back to the new newest.
	let selected = $derived(filtered.find((r) => r.id === selectedId) ?? filtered[0] ?? null);

	// The label for a run's list row: the book for an extraction, else the task name.
	function rowLabel(run: TaskRun): string {
		return run.task_type === 'extraction'
			? cleanTitle(run.book_title ?? 'Extraction')
			: TYPE_LABELS[run.task_type];
	}
</script>

<section
	class="panel"
	data-verify-unit="task-runs-panel"
	data-verify-total={runs.length}
	data-verify-count={filtered.length}
	data-verify-filter={filter}
	data-verify-empty={filtered.length === 0 ? 'true' : 'false'}
	data-verify-selected={selected?.id ?? ''}
	data-verify-first={filtered[0]?.id ?? ''}
	data-verify-statuses={filtered.map((r) => r.status).join(',')}
>
	{#if runs.length === 0}
		<p class="empty">No task runs yet.</p>
	{:else}
		<div class="filters" role="group" aria-label="Filter task runs by type">
			{#each FILTERS as f (f.id)}
				<button
					type="button"
					class="chip"
					class:active={filter === f.id}
					data-filter={f.id}
					aria-pressed={filter === f.id}
					onclick={() => (filter = f.id)}
				>
					{f.label}
				</button>
			{/each}
		</div>

		<p class="count mono">{filtered.length} {filtered.length === 1 ? 'run' : 'runs'}</p>

		{#if filtered.length === 0}
			<p class="empty">No runs of this type.</p>
		{:else}
			<div class="layout">
				<ul class="runs">
					{#each filtered as run (run.id)}
						<li>
							<button
								type="button"
								class="run-row"
								class:selected={selected?.id === run.id}
								data-run-id={run.id}
								data-task-type={run.task_type}
								aria-current={selected?.id === run.id ? 'true' : undefined}
								onclick={() => (selectedId = run.id)}
							>
								<span class="row-main">
									<span class="row-title">{rowLabel(run)}</span>
									<span class="row-sub mono"
										>{rowDate(run.created_at)} · {rowSummary(run)}</span
									>
								</span>
								<TaskStatusBadge status={run.status} />
							</button>
						</li>
					{/each}
				</ul>

				<div class="report">
					<TaskRunDetail run={selected} />
				</div>
			</div>
		{/if}
	{/if}
</section>

<style>
	.panel {
		min-width: 0;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 0 0 1.25rem;
	}
	.chip {
		font-family: var(--f-mono);
		font-size: 0.66rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
		background: transparent;
		border: 1px solid var(--line-strong);
		border-radius: 999px;
		padding: 0.35rem 0.8rem;
		cursor: pointer;
		transition:
			color 0.15s var(--ease-out),
			border-color 0.15s var(--ease-out),
			background 0.15s var(--ease-out);
	}
	.chip:hover {
		color: var(--ink);
		border-color: var(--ink);
	}
	.chip.active {
		color: var(--bg);
		background: var(--ink);
		border-color: var(--ink);
	}
	.chip:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.count {
		color: var(--muted);
		margin: 0 0 1.25rem;
	}

	.layout {
		display: grid;
		grid-template-columns: minmax(0, 23rem) minmax(0, 1fr);
		gap: 2rem var(--col-gap);
		align-items: start;
	}

	.runs {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: var(--border);
	}

	.run-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		border-bottom: var(--border);
		border-left: 2px solid transparent;
		padding: 0.85rem 0.85rem 0.85rem 0.6rem;
		cursor: pointer;
		transition:
			background 0.15s var(--ease-out),
			border-color 0.15s var(--ease-out);
	}
	.run-row:hover {
		background: var(--bg-warm);
	}
	.run-row.selected {
		background: var(--bg-warm);
		border-left-color: var(--accent);
	}
	.run-row:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	.row-main {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		min-width: 0;
	}
	.row-title {
		font-family: var(--f-serif);
		font-size: 1rem;
		color: var(--ink);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.row-sub {
		color: var(--muted);
		font-size: 0.68rem;
	}

	.report {
		min-width: 0;
		padding-top: 0.25rem;
	}

	.empty {
		font-family: var(--f-serif);
		font-size: 1.3rem;
		color: var(--muted);
		margin: 0;
		padding: 2rem 0;
	}

	@media (max-width: 860px) {
		.layout {
			grid-template-columns: 1fr;
			gap: 2rem;
		}
		.row-title {
			white-space: normal;
		}
	}
</style>
