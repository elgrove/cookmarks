<script module lang="ts">
	import type { ExtractionRun } from '$lib/api/extraction';

	export type ExtractionStatus = ExtractionRun['status'];

	export type ExtractionStatusBadgeProps = {
		status: ExtractionStatus;
	};

	const LABELS: Record<ExtractionStatus, string> = {
		queued: 'Queued',
		running: 'Running',
		review: 'Review',
		done: 'Done',
		failed: 'Failed'
	};
</script>

<script lang="ts">
	let { status }: ExtractionStatusBadgeProps = $props();
</script>

<span class="badge {status}">{LABELS[status]}</span>

<style>
	.badge {
		display: inline-block;
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		padding: 0.2rem 0.5rem;
		border-radius: 3px;
		white-space: nowrap;
	}
	.queued {
		color: var(--muted);
		background: var(--bg-warm);
	}
	.running {
		color: var(--chip-blue-c);
		background: var(--chip-blue);
	}
	.review {
		color: var(--clay-deep);
		background: var(--chip-clay);
	}
	.done {
		color: var(--chip-green-c);
		background: var(--chip-green);
	}
	.failed {
		color: var(--bg);
		background: var(--clay-deep);
	}
</style>
