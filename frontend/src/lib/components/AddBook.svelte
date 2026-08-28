<script module lang="ts">
	import type { StagedBook, IngestRequest } from '$lib/api/ingest';
	import type { TaskRun, BookIngestDetail } from '$lib/api/task-runs';

	export type AddBookProps = {
		/** Recent book-ingest runs, newest first. Network-free and verifiable in
		 *  isolation; the route owns the fetching and the polling. */
		runs?: TaskRun[];
		onStageFile?: (file: File) => Promise<StagedBook>;
		onStageUrl?: (url: string) => Promise<StagedBook>;
		onSubmit?: (request: IngestRequest) => Promise<void>;
	};

	export type AddBookStage = 'idle' | 'staging' | 'staged' | 'submitting';

	const runDateFmt = new Intl.DateTimeFormat('en-GB', {
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});

	function runDate(iso: string): string {
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? '—' : runDateFmt.format(d);
	}

	function ingestDetail(run: TaskRun): BookIngestDetail {
		return run.detail as unknown as BookIngestDetail;
	}

	/** The book this run collided with, if it failed as a duplicate — the one case a
	 *  failure is answerable, by replacing the copy already in the library. */
	function duplicateOf(run: TaskRun): string | null {
		if (run.status !== 'failed') return null;
		return ingestDetail(run).duplicate_of_book_id ?? null;
	}
</script>

<script lang="ts">
	import TaskStatusBadge from './TaskStatusBadge.svelte';

	let { runs = [], onStageFile, onStageUrl, onSubmit }: AddBookProps = $props();

	let stage = $state<AddBookStage>('idle');
	let staged = $state<StagedBook | null>(null);
	let title = $state('');
	let author = $state('');
	let extract = $state(false);
	let url = $state('');
	let error = $state('');
	let dragging = $state(false);
	let replacing = $state<string | null>(null);

	let canSubmit = $derived(title.trim().length > 0 && author.trim().length > 0);
	let offers = $derived(runs.filter((r) => duplicateOf(r) !== null).length);

	function accept(book: StagedBook) {
		staged = book;
		title = book.title;
		author = book.author;
		extract = false;
		stage = 'staged';
	}

	function reset() {
		staged = null;
		title = '';
		author = '';
		extract = false;
		url = '';
		stage = 'idle';
	}

	async function stageWith(work: () => Promise<StagedBook>) {
		error = '';
		stage = 'staging';
		try {
			accept(await work());
		} catch (err) {
			error = err instanceof Error ? err.message : 'That file could not be read.';
			stage = 'idle';
		}
	}

	function chooseFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (file && onStageFile) stageWith(() => onStageFile(file));
	}

	function dropFile(event: DragEvent) {
		event.preventDefault();
		dragging = false;
		const file = event.dataTransfer?.files?.[0];
		if (file && onStageFile) stageWith(() => onStageFile(file));
	}

	function submitUrl(event: Event) {
		event.preventDefault();
		if (url.trim() && onStageUrl) stageWith(() => onStageUrl(url.trim()));
	}

	async function submit(event: Event) {
		event.preventDefault();
		if (!staged || !canSubmit || !onSubmit) return;
		error = '';
		stage = 'submitting';
		try {
			await onSubmit({
				staging_id: staged.staging_id,
				title: title.trim(),
				author: author.trim(),
				extract
			});
			reset();
		} catch (err) {
			error = err instanceof Error ? err.message : 'That book could not be queued.';
			stage = 'staged';
		}
	}

	async function replace(run: TaskRun) {
		const bookId = duplicateOf(run);
		const detail = ingestDetail(run);
		if (!bookId || !onSubmit) return;
		error = '';
		replacing = null;
		try {
			await onSubmit({
				staging_id: detail.staging_id,
				title: detail.title,
				author: detail.author,
				extract: detail.extract ?? false,
				replace_book_id: bookId
			});
		} catch (err) {
			error = err instanceof Error ? err.message : 'The replacement could not be queued.';
		}
	}
</script>

<section
	class="add-book"
	data-verify-unit="add-book"
	data-verify-stage={stage}
	data-verify-run-count={runs.length}
	data-verify-can-submit={canSubmit ? 'true' : 'false'}
	data-verify-duplicate-offers={offers}
	data-verify-error={error}
	data-verify-staged-format={staged?.format ?? ''}
	data-verify-no-extraction="false"
>
	<header class="masthead">
		<p class="eyebrow">Library</p>
		<h1>Add a book</h1>
		<p class="standfirst">
			Upload a cookbook or paste a download link. EPUBs and PDFs are kept as they are;
			anything else Calibre can convert becomes an EPUB. Its cover and details come from
			the file itself.
		</p>
	</header>

	{#if stage === 'staged' || stage === 'submitting'}
		<form class="confirm" onsubmit={submit}>
			<p class="eyebrow">01 — Confirm</p>
			<p class="file mono">{staged?.filename} · {staged?.format.toUpperCase()}</p>

			<label class="field">
				<span>Title</span>
				<input bind:value={title} name="title" required disabled={stage === 'submitting'} />
			</label>

			<label class="field">
				<span>Author</span>
				<input bind:value={author} name="author" required disabled={stage === 'submitting'} />
			</label>

			<label class="check">
				<input
					type="checkbox"
					bind:checked={extract}
					disabled={stage === 'submitting'}
				/>
				Extract recipes once it is added
			</label>

			<div class="actions">
				<button class="btn primary" type="submit" disabled={!canSubmit || stage === 'submitting'}>
					{stage === 'submitting' ? 'Adding…' : 'Add to library'}
				</button>
				<button class="btn ghost" type="button" onclick={reset} disabled={stage === 'submitting'}>
					Choose another file
				</button>
			</div>
		</form>
	{:else}
		<div class="intake">
			<label
				class="drop"
				class:dragging
				class:busy={stage === 'staging'}
				ondragover={(e) => {
					e.preventDefault();
					dragging = true;
				}}
				ondragleave={() => (dragging = false)}
				ondrop={dropFile}
			>
				<span class="drop-title">
					{stage === 'staging' ? 'Reading the file…' : 'Drop a book here'}
				</span>
				<span class="drop-sub mono">EPUB · MOBI · AZW3 · and anything else Calibre converts</span>
				<input
					type="file"
					class="file-input"
					aria-label="Choose a book file"
					onchange={chooseFile}
					disabled={stage === 'staging'}
				/>
			</label>

			<form class="url" onsubmit={submitUrl}>
				<label class="field">
					<span>Or a download link</span>
					<input
						bind:value={url}
						name="url"
						type="url"
						placeholder="https://…"
						disabled={stage === 'staging'}
					/>
				</label>
				<button class="btn ghost" type="submit" disabled={!url.trim() || stage === 'staging'}>
					Fetch
				</button>
			</form>
		</div>
	{/if}

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}

	<section class="runs">
		<p class="eyebrow">Recently added</p>
		{#if runs.length === 0}
			<p class="empty">No books added yet.</p>
		{:else}
			<ul>
				{#each runs as run, i (run.id)}
					{@const detail = ingestDetail(run)}
					{@const duplicate = duplicateOf(run)}
					<li data-run-id={run.id} data-verify-run-status={run.status}>
						<div class="run-row">
							<span class="index mono">{String(i + 1).padStart(2, '0')}</span>
							<span class="run-main">
								<span class="run-title">{detail.title || 'Untitled'}</span>
								<span class="run-sub mono">
									{runDate(run.created_at)}{#if detail.author} · {detail.author}{/if}
								</span>
								{#if run.errors.length > 0}
									<span class="run-error">{run.errors[run.errors.length - 1]}</span>
								{/if}
							</span>
							<TaskStatusBadge status={run.status} />
						</div>

						{#if duplicate}
							<div class="duplicate" data-verify-duplicate-offer="true">
								{#if replacing === run.id}
									<p class="prompt">
										Replace it? The copy in the library is deleted for good. Its recipes,
										favourites and lists stay.
									</p>
									<button class="btn danger" type="button" onclick={() => replace(run)}>
										Delete existing and replace
									</button>
									<button class="btn ghost" type="button" onclick={() => (replacing = null)}>
										Keep both
									</button>
								{:else}
									<button
										class="btn ghost"
										type="button"
										onclick={() => (replacing = run.id)}
									>
										Delete existing and replace
									</button>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</section>

<style>
	.add-book {
		min-width: 0;
	}

	.masthead {
		max-width: 34rem;
		margin: 0 0 2.5rem;
	}
	.eyebrow {
		font-family: var(--f-mono);
		font-size: 0.66rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 0 0 0.6rem;
	}
	h1 {
		font-family: var(--f-serif);
		font-size: clamp(2rem, 5vw, 3rem);
		font-weight: 400;
		line-height: 1.05;
		margin: 0 0 0.75rem;
	}
	.standfirst {
		font-family: var(--f-serif);
		color: var(--muted);
		line-height: 1.6;
		margin: 0;
	}

	.intake {
		display: grid;
		grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
		gap: var(--col-gap);
		align-items: start;
		margin-bottom: 2.5rem;
	}

	.drop {
		display: flex;
		flex-direction: column;
		justify-content: center;
		gap: 0.5rem;
		min-height: 12rem;
		padding: 2rem;
		border: 1px dashed var(--line-strong);
		background: var(--bg-warm);
		cursor: pointer;
		transition:
			border-color 0.15s var(--ease-out),
			background 0.15s var(--ease-out);
	}
	.drop:hover,
	.drop.dragging {
		border-color: var(--clay);
	}
	.drop.busy {
		cursor: progress;
	}
	.drop:focus-within {
		outline: 2px solid var(--clay);
		outline-offset: 2px;
	}
	.drop-title {
		font-family: var(--f-serif);
		font-size: 1.4rem;
		color: var(--ink);
	}
	.drop-sub {
		font-size: 0.68rem;
		color: var(--muted);
	}
	.file-input {
		margin-top: 0.75rem;
		font-family: var(--f-mono);
		font-size: 0.7rem;
		color: var(--muted);
	}

	.url {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
		align-items: flex-start;
	}

	.confirm {
		display: flex;
		flex-direction: column;
		gap: 1.1rem;
		max-width: 34rem;
		margin-bottom: 2.5rem;
		padding: 1.75rem;
		border: var(--border);
		background: var(--bg-warm);
	}
	.file {
		font-size: 0.68rem;
		color: var(--muted);
		margin: -0.4rem 0 0;
		overflow-wrap: anywhere;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		width: 100%;
	}
	.field span {
		font-family: var(--f-mono);
		font-size: 0.66rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
	}
	.field input {
		font-family: var(--f-serif);
		font-size: 1.05rem;
		color: var(--ink);
		background: var(--bg);
		border: 1px solid var(--line-strong);
		padding: 0.6rem 0.7rem;
		width: 100%;
	}
	.field input:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: -1px;
	}

	.check {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--muted);
	}
	.check input {
		accent-color: var(--clay);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.8rem;
		padding: 0.55rem 1.1rem;
		border: 1px solid var(--ink);
		background: transparent;
		color: var(--ink);
		cursor: pointer;
		transition:
			background 0.15s var(--ease-out),
			color 0.15s var(--ease-out),
			border-color 0.15s var(--ease-out);
	}
	.btn.primary {
		background: var(--ink);
		color: var(--bg);
	}
	.btn.ghost {
		border-color: var(--line-strong);
		color: var(--muted);
	}
	.btn.ghost:hover:not(:disabled) {
		border-color: var(--ink);
		color: var(--ink);
	}
	.btn.danger {
		border-color: var(--clay);
		background: var(--clay);
		color: var(--bg);
	}
	.btn:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.btn:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: 2px;
	}

	.error {
		font-family: var(--f-serif);
		color: var(--clay);
		margin: 0 0 2rem;
	}

	.runs ul {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: var(--border);
	}
	.runs li {
		border-bottom: var(--border);
		padding: 0.9rem 0;
	}
	.run-row {
		display: flex;
		align-items: baseline;
		gap: 1rem;
	}
	.index {
		font-size: 0.7rem;
		color: var(--clay);
	}
	.run-main {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		flex: 1;
		min-width: 0;
	}
	.run-title {
		font-family: var(--f-serif);
		font-size: 1.05rem;
		color: var(--ink);
	}
	.run-sub {
		font-size: 0.68rem;
		color: var(--muted);
	}
	.run-error {
		font-family: var(--f-grotesk);
		font-size: 0.8rem;
		color: var(--clay);
	}

	.duplicate {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		margin: 0.75rem 0 0 2.4rem;
	}
	.duplicate .prompt {
		font-family: var(--f-serif);
		font-size: 0.95rem;
		color: var(--muted);
		margin: 0;
		flex-basis: 100%;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		margin: 0;
		padding: 1.5rem 0;
	}

	@media (max-width: 860px) {
		.intake {
			grid-template-columns: 1fr;
			gap: 1.5rem;
		}
	}
</style>
