<script module lang="ts">
	import type {
		RecipeEnrichmentBackfillDetail,
		TaskStatus
	} from '$lib/api/task-runs';

	export type BackfillProgressProps = {
		/** The backfill run's `detail` payload — aggregate counts, chunks, usage and cost. */
		detail: RecipeEnrichmentBackfillDetail;
		/** The parent run's lifecycle status, for the waiting/running headline. */
		status: TaskStatus;
	};

	export type BackfillPhase =
		| 'prepared'
		| 'waiting'
		| 'partial'
		| 'complete'
		| 'terminal'
		| 'stale';

	/** One phase for the whole panel, so the verify contract can pin it. Terminal
	 *  failure wins over stale; stale wins over partial progress. */
	export function phaseOf(detail: RecipeEnrichmentBackfillDetail): BackfillPhase {
		const applied = detail.applied ?? 0;
		const failed = detail.terminal_failed ?? 0;
		const stale = detail.stale ?? 0;
		const prepared = detail.prepared ?? 0;
		const submitted = detail.submitted ?? 0;
		if (failed > 0) return 'terminal';
		if (stale > 0) return 'stale';
		if (applied > 0 && applied + stale + failed < prepared) return 'partial';
		if (applied > 0 && prepared > 0 && applied >= prepared) return 'complete';
		if (submitted > 0) return 'waiting';
		return 'prepared';
	}

	function count(n: number | undefined): string {
		return typeof n === 'number' ? String(n) : '—';
	}
</script>

<script lang="ts">
	let { detail, status }: BackfillProgressProps = $props();

	let phase = $derived(phaseOf(detail));
	let chunks = $derived(
		Object.entries(detail.chunks_by_state ?? {})
			.map(([state, n]) => `${state} ${n}`)
			.join(' · ') || '—'
	);
</script>

<section
	class="progress"
	data-verify-unit="enrichment-backfill-progress"
	data-verify-phase={phase}
	data-verify-status={status}
	data-verify-applied={detail.applied ?? 0}
	data-verify-failed={detail.terminal_failed ?? 0}
	data-verify-stale={detail.stale ?? 0}
	data-verify-cost={detail.cost_estimate_usd ?? ''}
	aria-label="Batch backfill progress"
>
	<p class="headline">
		{#if phase === 'complete'}
			Backfill complete — {detail.applied} of {detail.prepared} recipes applied.
		{:else if phase === 'terminal'}
			Backfill stopped with {detail.terminal_failed} terminal failure{detail.terminal_failed === 1
				? ''
				: 's'} — {detail.applied ?? 0} applied, kept.
		{:else if phase === 'stale'}
			{detail.stale} recipe{detail.stale === 1 ? '' : 's'} changed mid-flight — resume a later run.
		{:else if phase === 'partial'}
			{detail.applied} of {detail.prepared} applied — {status === 'waiting'
				? 'waiting on remote jobs'
				: 'applying results'}.
		{:else if phase === 'waiting'}
			{detail.submitted} of {detail.prepared} submitted — waiting on remote jobs.
		{:else}
			Prepared {detail.prepared ?? 0} recipes — submission pending.
		{/if}
	</p>
	<dl class="meta">
		<div class="row"><dt>Selected</dt><dd>{count(detail.selected)}</dd></div>
		<div class="row"><dt>Submitted</dt><dd>{count(detail.submitted)}</dd></div>
		<div class="row"><dt>Succeeded</dt><dd>{count(detail.succeeded)}</dd></div>
		<div class="row"><dt>Applied</dt><dd>{count(detail.applied)}</dd></div>
		<div class="row"><dt>Stale</dt><dd>{count(detail.stale)}</dd></div>
		<div class="row"><dt>Terminal failures</dt><dd>{count(detail.terminal_failed)}</dd></div>
		<div class="row"><dt>Chunks</dt><dd>{chunks}</dd></div>
		<div class="row">
			<dt>Cost estimate</dt>
			<dd>
				{detail.cost_estimate_usd !== undefined
					? `$${detail.cost_estimate_usd} (snapshot ${detail.pricing_snapshot_version ?? '—'})`
					: '—'}
			</dd>
		</div>
		{#if detail.next_poll_in_seconds !== undefined && detail.next_poll_in_seconds !== null}
			<div class="row"><dt>Next poll</dt><dd>in {detail.next_poll_in_seconds}s</dd></div>
		{/if}
		{#if detail.last_provider_error}
			<div class="row"><dt>Last provider error</dt><dd class="wrap">{detail.last_provider_error}</dd></div>
		{/if}
	</dl>
</section>

<style>
	.progress {
		border-top: var(--border-strong);
		padding-top: 1rem;
		margin-top: 1rem;
	}
	.headline {
		font-family: var(--f-grotesk);
		font-size: 0.92rem;
		line-height: 1.6;
		margin: 0 0 0.75rem;
	}
	.meta {
		display: grid;
		gap: 0.4rem;
		margin: 0;
	}
	.row {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		font-family: var(--f-mono);
		font-size: 0.76rem;
	}
	.row dt {
		color: var(--muted);
	}
	.row dd {
		margin: 0;
		text-align: right;
	}
	.row dd.wrap {
		overflow-wrap: anywhere;
	}
</style>
