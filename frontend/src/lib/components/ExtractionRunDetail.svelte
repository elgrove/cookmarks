<script module lang="ts">
	import type { ExtractionRun } from '$lib/api/extraction';

	export type ExtractionRunDetailProps = {
		/** The run to report on, or null when nothing is selected — the component renders
		 *  a calm "no run selected" state in that case. Network-free and verifiable in
		 *  isolation; the admin route owns the fetch and selection. */
		run?: ExtractionRun | null;
	};

	const METHOD_LABELS: Record<string, string> = { file: 'File', block: 'Block' };

	const dateFmt = new Intl.DateTimeFormat('en-GB', {
		day: 'numeric',
		month: 'short',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	});

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? '—' : dateFmt.format(d);
	}

	function formatChapters(processed: number, total: number): string {
		if (total > 0) return `${processed} / ${total}`;
		if (processed > 0) return String(processed);
		return '—';
	}

	function formatCost(cost: string | null): string {
		return cost === null ? '—' : `$${cost}`;
	}

	function formatTokens(input: number | null, output: number | null): string {
		if (input === null && output === null) return '—';
		const parts: string[] = [];
		if (input !== null) parts.push(`${input.toLocaleString('en-GB')} in`);
		if (output !== null) parts.push(`${output.toLocaleString('en-GB')} out`);
		return parts.join(' · ');
	}

	function formatDuration(run: ExtractionRun): string {
		if (!run.started_at || !run.completed_at) return '—';
		const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
		if (Number.isNaN(ms) || ms < 0) return '—';
		const secs = Math.round(ms / 1000);
		if (secs < 60) return `${secs}s`;
		const mins = Math.floor(secs / 60);
		return `${mins}m ${secs % 60}s`;
	}
</script>

<script lang="ts">
	import ExtractionStatusBadge from './ExtractionStatusBadge.svelte';
	import { cleanTitle } from '$lib/title';

	let { run = null }: ExtractionRunDetailProps = $props();
</script>

<section
	class="detail"
	data-verify-unit="extraction-run-detail"
	data-verify-has-run={run ? 'true' : 'false'}
	data-verify-status={run ? run.status : 'none'}
	data-verify-error-count={run ? run.errors.length : 0}
>
	{#if run}
		<header class="head">
			<div class="titles">
				<p class="eyebrow">Extraction run</p>
				<h3 class="title">{cleanTitle(run.book_title)}</h3>
			</div>
			<ExtractionStatusBadge status={run.status} />
		</header>

		<dl class="meta">
			<div class="row">
				<dt>Method</dt>
				<dd>{run.extraction_method ? METHOD_LABELS[run.extraction_method] : '—'}</dd>
			</div>
			<div class="row">
				<dt>Provider</dt>
				<dd>{run.provider_name ?? '—'}</dd>
			</div>
			<div class="row">
				<dt>Model</dt>
				<dd class="wrap">{run.model_name ?? '—'}</dd>
			</div>
			<div class="row">
				<dt>Chapters</dt>
				<dd>{formatChapters(run.chapters_processed, run.total_chapters)}</dd>
			</div>
			<div class="row">
				<dt>Recipes found</dt>
				<dd>{run.recipes_found}</dd>
			</div>
			<div class="row">
				<dt>Cost</dt>
				<dd>{formatCost(run.cost_usd)}</dd>
			</div>
			<div class="row">
				<dt>Tokens</dt>
				<dd>{formatTokens(run.input_tokens, run.output_tokens)}</dd>
			</div>
			<div class="row">
				<dt>Started</dt>
				<dd>{formatDate(run.started_at)}</dd>
			</div>
			<div class="row">
				<dt>Completed</dt>
				<dd>{formatDate(run.completed_at)}</dd>
			</div>
			<div class="row">
				<dt>Duration</dt>
				<dd>{formatDuration(run)}</dd>
			</div>
		</dl>

		{#if run.pending_question}
			<p class="awaiting">
				Awaiting review — answer “{run.pending_question.question}” on the book page to resume.
			</p>
		{/if}

		{#if run.errors.length > 0}
			<div class="errors">
				<p class="errors-label">
					{run.errors.length} error{run.errors.length === 1 ? '' : 's'}
				</p>
				<ul class="error-list">
					{#each run.errors as error, i (i)}
						<li class="error">{error}</li>
					{/each}
				</ul>
			</div>
		{/if}
	{:else}
		<p class="empty">Select a run to see its report.</p>
	{/if}
</section>

<style>
	.detail {
		min-width: 0;
	}
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		padding-bottom: 1rem;
		border-bottom: var(--border-strong);
	}
	.titles {
		min-width: 0;
	}
	.eyebrow {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 0 0 0.3rem;
	}
	.title {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: 1.5rem;
		line-height: 1.15;
		color: var(--ink);
		margin: 0;
		overflow-wrap: anywhere;
	}

	.meta {
		margin: 0;
		padding: 0;
	}
	.row {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1.5rem;
		padding: 0.6rem 0;
		border-bottom: var(--border);
	}
	.row dt {
		font-family: var(--f-mono);
		font-size: 0.68rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
		flex: none;
	}
	.row dd {
		font-family: var(--f-mono);
		font-size: 0.82rem;
		color: var(--ink);
		margin: 0;
		text-align: right;
	}
	.row dd.wrap {
		overflow-wrap: anywhere;
	}

	.awaiting {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		line-height: 1.5;
		color: var(--clay-deep);
		background: var(--chip-clay);
		border-left: 3px solid var(--clay);
		border-radius: 3px;
		padding: 0.7rem 0.9rem;
		margin: 1.25rem 0 0;
	}

	.errors {
		margin-top: 1.5rem;
	}
	.errors-label {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--clay-deep);
		margin: 0 0 0.5rem;
	}
	.error-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.error {
		font-family: var(--f-mono);
		font-size: 0.78rem;
		line-height: 1.5;
		color: var(--ink);
		background: var(--bg-warm);
		border-left: 3px solid var(--clay-deep);
		border-radius: 3px;
		padding: 0.55rem 0.8rem;
		overflow-wrap: anywhere;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.2rem;
		color: var(--muted);
		margin: 0;
		padding: 2rem 0;
	}
</style>
