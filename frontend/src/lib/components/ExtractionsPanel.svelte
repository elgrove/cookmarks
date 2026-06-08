<script module lang="ts">
	import type { ExtractionRun } from '$lib/api/extraction';

	export type ExtractionsPanelProps = {
		/** Every extraction run, newest first (the server's order is preserved). Network-free
		 *  and verifiable in isolation; the admin route owns the fetch. */
		runs: ExtractionRun[];
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
</script>

<script lang="ts">
	import ExtractionStatusBadge from './ExtractionStatusBadge.svelte';
	import ExtractionRunDetail from './ExtractionRunDetail.svelte';

	let { runs }: ExtractionsPanelProps = $props();

	let selectedId = $state<string | null>(null);

	// Default to the newest run so a report is shown on open; an explicit click overrides.
	let selected = $derived(runs.find((r) => r.id === selectedId) ?? runs[0] ?? null);
</script>

<section
	class="panel"
	data-verify-unit="extractions-panel"
	data-verify-count={runs.length}
	data-verify-empty={runs.length === 0 ? 'true' : 'false'}
	data-verify-selected={selected?.id ?? ''}
	data-verify-first={runs[0]?.id ?? ''}
	data-verify-statuses={runs.map((r) => r.status).join(',')}
>
	{#if runs.length === 0}
		<p class="empty">No extraction runs yet.</p>
	{:else}
		<p class="count mono">{runs.length} {runs.length === 1 ? 'run' : 'runs'}</p>
		<div class="layout">
			<ul class="runs">
				{#each runs as run (run.id)}
					<li>
						<button
							type="button"
							class="run-row"
							class:selected={selected?.id === run.id}
							data-run-id={run.id}
							aria-current={selected?.id === run.id ? 'true' : undefined}
							onclick={() => (selectedId = run.id)}
						>
							<span class="row-main">
								<span class="row-title">{run.book_title}</span>
								<span class="row-sub mono"
									>{rowDate(run.created_at)} · {run.recipes_found} recipes</span
								>
							</span>
							<ExtractionStatusBadge status={run.status} />
						</button>
					</li>
				{/each}
			</ul>

			<div class="report">
				<ExtractionRunDetail run={selected} />
			</div>
		</div>
	{/if}
</section>

<style>
	.panel {
		min-width: 0;
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
		border-left-color: var(--clay);
	}
	.run-row:focus-visible {
		outline: 2px solid var(--clay);
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
		font-style: italic;
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
