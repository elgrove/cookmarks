<script module lang="ts">
	import type { TaskStatus } from '$lib/api/task-runs';

	export type TaskStatusBadgeProps = {
		status: TaskStatus;
	};

	const LABELS: Record<TaskStatus, string> = {
		queued: 'Queued',
		running: 'Running',
		waiting: 'Waiting',
		review: 'Review',
		done: 'Done',
		failed: 'Failed'
	};
</script>

<script lang="ts">
	let { status }: TaskStatusBadgeProps = $props();
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
	.waiting {
		color: var(--accent-deep);
		background: var(--bg-warm);
	}
	.review {
		color: var(--accent-deep);
		background: var(--chip-accent);
	}
	.done {
		color: var(--chip-green-c);
		background: var(--chip-green);
	}
	.failed {
		color: var(--bg);
		background: var(--danger);
	}
</style>
