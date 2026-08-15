<script lang="ts">
	import { onMount } from 'svelte';
	import AddBook from '$lib/components/AddBook.svelte';
	import { stageFile, stageUrl, submitIngest, type IngestRequest } from '$lib/api/ingest';
	import { fetchTaskRuns, type TaskRun } from '$lib/api/task-runs';
	import { pageTitle } from '$lib/title';

	const POLL_MS = 3000;

	let runs = $state<TaskRun[]>([]);
	let timer: ReturnType<typeof setTimeout> | null = null;

	// Poll only while something is in flight: an ingest converts, fetches metadata and
	// syncs, so its run is worth watching, but a settled list is not worth waking for.
	let inFlight = $derived(runs.some((r) => r.status === 'queued' || r.status === 'running'));

	async function load() {
		try {
			runs = await fetchTaskRuns('book_ingest');
		} catch (err) {
			console.error('failed to load ingest runs', err);
		}
	}

	function schedule() {
		if (timer) clearTimeout(timer);
		timer = setTimeout(async () => {
			await load();
			if (inFlight) schedule();
		}, POLL_MS);
	}

	async function submit(request: IngestRequest) {
		await submitIngest(request);
		await load();
		schedule();
	}

	onMount(() => {
		load().then(() => {
			if (inFlight) schedule();
		});
		return () => {
			if (timer) clearTimeout(timer);
		};
	});
</script>

<svelte:head>
	<title>{pageTitle('Add a book')}</title>
</svelte:head>

<section class="page">
	<AddBook
		{runs}
		onStageFile={(file) => stageFile(file)}
		onStageUrl={(url) => stageUrl(url)}
		onSubmit={submit}
	/>
</section>

<style>
	.page {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}
</style>
