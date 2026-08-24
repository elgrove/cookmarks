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

	export type TaskRunDetailProps = {
		/** The run to report on, or null when nothing is selected — the component renders
		 *  a calm "no run selected" state in that case. Network-free and verifiable in
		 *  isolation; the admin route owns the fetch and selection. */
		run?: TaskRun | null;
	};

	type Row = { label: string; value: string; wrap?: boolean };

	const METHOD_LABELS: Record<string, string> = { file: 'File', block: 'Block' };

	// Short eyebrow label + a serif title for the non-extraction types (extraction's
	// title is the book it ran against).
	const TYPE_LABELS: Record<TaskType, string> = {
		extraction: 'Extraction',
		book_keywords: 'Book keywords',
		keyword_dedup: 'Keyword dedup',
		calibre_sync: 'Calibre sync',
		book_ingest: 'Add book'
	};
	const TYPE_TITLES: Record<Exclude<TaskType, 'extraction'>, string> = {
		book_keywords: 'Book-keyword tagging',
		keyword_dedup: 'Keyword vocabulary dedup',
		calibre_sync: 'Calibre library sync',
		book_ingest: 'Book added to the library'
	};

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

	function formatDuration(run: TaskRun): string {
		if (!run.started_at || !run.completed_at) return '—';
		const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
		if (Number.isNaN(ms) || ms < 0) return '—';
		const secs = Math.round(ms / 1000);
		if (secs < 60) return `${secs}s`;
		const mins = Math.floor(secs / 60);
		return `${mins}m ${secs % 60}s`;
	}

	function count(n: number | undefined): string {
		return typeof n === 'number' ? String(n) : '—';
	}

	// The type-specific report rows, read from the run's `detail` payload. Defensive
	// against a still-queued run whose detail isn't populated yet.
	function metaRows(run: TaskRun): Row[] {
		switch (run.task_type) {
			case 'extraction': {
				const d = run.detail as unknown as ExtractionDetail;
				return [
					{ label: 'Method', value: d.extraction_method ? METHOD_LABELS[d.extraction_method] : '—' },
					{ label: 'Provider', value: run.provider_name ?? '—' },
					{ label: 'Model', value: run.model_name ?? '—', wrap: true },
					{ label: 'Chapters', value: formatChapters(d.chapters_processed, d.total_chapters) },
					{ label: 'Recipes found', value: count(d.recipes_found) },
					{ label: 'Cost', value: formatCost(run.cost_usd) },
					{ label: 'Tokens', value: formatTokens(run.input_tokens, run.output_tokens) }
				];
			}
			case 'book_keywords': {
				const d = run.detail as unknown as BookKeywordsDetail;
				return [
					{ label: 'Books tagged', value: count(d.books_tagged) },
					{ label: 'Regenerate', value: d.regenerate ? 'Yes' : 'No' }
				];
			}
			case 'keyword_dedup': {
				const d = run.detail as unknown as KeywordDedupDetail;
				const rows: Row[] = [
					{ label: 'Keywords analysed', value: count(d.keywords_in) },
					{ label: 'Candidates', value: count(d.candidates) },
					{ label: 'Merges applied', value: count(d.merges_applied) },
					{ label: 'Deterministic merges', value: count(d.pre_merges) },
					{ label: 'AI merges', value: count(d.ai_merges) },
					{ label: 'Keywords removed', value: count(d.keywords_removed) }
				];
				if (d.ai_truncated) rows.push({ label: 'AI reply', value: 'Truncated — salvaged' });
				return rows;
			}
			case 'calibre_sync': {
				const d = run.detail as unknown as CalibreSyncDetail;
				return [
					{ label: 'Created', value: count(d.created?.length) },
					{ label: 'Updated', value: count(d.updated?.length) },
					{ label: 'Orphaned', value: count(d.orphaned?.length) },
					{ label: 'Deleted', value: count(d.deleted?.length) },
					{ label: 'Excluded', value: count(d.excluded?.length) }
				];
			}
			case 'book_ingest': {
				const d = run.detail as unknown as BookIngestDetail;
				return [
					{ label: 'Title', value: d.title || '—', wrap: true },
					{ label: 'Author', value: d.author || '—', wrap: true },
					{ label: 'Source format', value: d.format ? d.format.toUpperCase() : '—' },
					{ label: 'Converted', value: d.converted ? 'Yes' : 'No' },
					{ label: 'Calibre id', value: count(d.calibre_id) },
					{ label: 'Cover', value: d.cover ? 'From the book' : 'None' },
					{ label: 'Extraction', value: d.extraction_queued ? 'Queued' : 'Not queued' }
				];
			}
		}
	}
</script>

<script lang="ts">
	import TaskStatusBadge from './TaskStatusBadge.svelte';
	import { cleanTitle } from '$lib/title';

	let { run = null }: TaskRunDetailProps = $props();

	let title = $derived(
		run
			? run.task_type === 'extraction'
				? cleanTitle(run.book_title ?? 'Extraction')
				: TYPE_TITLES[run.task_type]
			: ''
	);
</script>

<section
	class="detail"
	data-verify-unit="task-run-detail"
	data-verify-has-run={run ? 'true' : 'false'}
	data-verify-task-type={run ? run.task_type : 'none'}
	data-verify-status={run ? run.status : 'none'}
	data-verify-error-count={run ? run.errors.length : 0}
	data-verify-ai-truncated={run?.task_type === 'keyword_dedup' &&
	(run.detail as unknown as KeywordDedupDetail).ai_truncated
		? 'true'
		: 'false'}
>
	{#if run}
		<header class="head">
			<div class="titles">
				<p class="eyebrow">{TYPE_LABELS[run.task_type]} run</p>
				<h3 class="title">{title}</h3>
			</div>
			<TaskStatusBadge status={run.status} />
		</header>

		<dl class="meta">
			{#each metaRows(run) as row (row.label)}
				<div class="row">
					<dt>{row.label}</dt>
					<dd class:wrap={row.wrap}>{row.value}</dd>
				</div>
			{/each}
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
