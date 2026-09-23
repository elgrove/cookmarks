<script module lang="ts">
	import type { BookMetadataUpdate } from '$lib/api/books';

	export type BookMetadataDraft = {
		title: string;
		author: string;
		isbn: string | null;
		pubdate: string | null;
		description: string;
		keywords: string[];
	};

	export type BookMetadataEditorProps = {
		/** The book's current metadata — the form's starting values. */
		initial: BookMetadataDraft;
		/** Injected so the component stays network-free and verifiable in isolation;
		 *  the book route wires this to PATCH /api/books/{id}. Awaited to drive
		 *  saving → closed, or → error if it rejects. May resolve with the
		 *  canonical metadata to display; the owner applies it. */
		onSave?: (update: BookMetadataUpdate) => Promise<Partial<BookMetadataDraft> | void>;
	};

	/** Split a keyword input on commas, trim, and drop blanks. */
	function splitKeywords(raw: string): string[] {
		return raw
			.split(',')
			.map((s) => s.trim())
			.filter((s) => s.length > 0);
	}
</script>

<script lang="ts">
	let { initial, onSave }: BookMetadataEditorProps = $props();

	let open = $state(false);
	let title = $state(initial.title);
	let author = $state(initial.author);
	let isbn = $state(initial.isbn ?? '');
	let pubdate = $state(initial.pubdate ?? '');
	let description = $state(initial.description ?? '');
	let keywords = $state<string[]>([...initial.keywords]);
	let keywordInput = $state('');
	let saving = $state(false);
	let error = $state('');

	// Required fields are non-blank after trimming.
	let valid = $derived(title.trim().length > 0 && author.trim().length > 0);

	function reset() {
		title = initial.title;
		author = initial.author;
		isbn = initial.isbn ?? '';
		pubdate = initial.pubdate ?? '';
		description = initial.description ?? '';
		keywords = [...initial.keywords];
		keywordInput = '';
		error = '';
	}

	function openForm() {
		reset();
		open = true;
	}

	function closeForm() {
		open = false;
		saving = false;
		error = '';
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') closeForm();
	}

	function commitKeywordInput() {
		const parts = splitKeywords(keywordInput);
		if (parts.length === 0) return;
		const seen = new Set(keywords.map((k) => k.toLowerCase()));
		for (const part of parts) {
			if (!seen.has(part.toLowerCase())) {
				seen.add(part.toLowerCase());
				keywords = [...keywords, part];
			}
		}
		keywordInput = '';
	}

	function removeKeyword(index: number) {
		keywords = keywords.filter((_, i) => i !== index);
	}

	// Commit comma-separated input as it is typed (and on blur/Enter) — the
	// harness `type` helper sets the whole string with one input event, so this
	// keeps typed commas tokenising without needing a separate blurus step.
	$effect(() => {
		if (keywordInput.includes(',')) commitKeywordInput();
	});

	async function save() {
		if (!valid || saving) return;
		saving = true;
		error = '';
		const update: BookMetadataUpdate = {
			title: title.trim(),
			author: author.trim(),
			isbn: isbn.trim() === '' ? null : isbn.trim(),
			pubdate: pubdate.trim() === '' ? null : pubdate.trim(),
			description: description.trim(),
			keywords: [...keywords]
		};
		try {
			const canonical = await onSave?.(update);
			if (canonical) {
				if (canonical.title !== undefined) title = canonical.title;
				if (canonical.author !== undefined) author = canonical.author;
				if (canonical.isbn !== undefined) isbn = canonical.isbn ?? '';
				if (canonical.pubdate !== undefined) pubdate = canonical.pubdate ?? '';
				if (canonical.description !== undefined) description = canonical.description ?? '';
				if (canonical.keywords !== undefined) keywords = [...canonical.keywords];
			}
			closeForm();
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : 'Could not save changes.';
			saving = false;
		}
	}
</script>

<svelte:window onkeydown={open ? onKeydown : undefined} />

<section
	class="editor"
	data-verify-unit="book-metadata-editor"
	data-verify-state={open ? 'open' : 'closed'}
	data-verify-valid={valid ? 'true' : 'false'}
	data-verify-saving={saving ? 'true' : 'false'}
	data-verify-error={error ? 'true' : 'false'}
	data-verify-keywords={keywords.length}
>
	<button type="button" class="btn ghost edit-open" onclick={openForm}
		>Edit book <span class="ar" aria-hidden="true">✎</span></button
	>
	{#if open}
		<div
			class="overlay"
			role="presentation"
			onclick={(e) => {
				if (e.target === e.currentTarget) closeForm();
			}}
		>
			<div class="panel" role="dialog" aria-modal="true" aria-labelledby="bme-heading">
				<header>
					<h2 id="bme-heading">Edit book</h2>
				</header>
				<form
					class="form"
					aria-label="Edit book details"
					onsubmit={(e) => {
						e.preventDefault();
						void save();
					}}
				>
					<div class="field">
						<label for="bme-title">Title</label>
						<input
							id="bme-title"
							name="title"
							type="text"
							class="edit-title"
							bind:value={title}
							required
							autocomplete="off"
						/>
					</div>
					<div class="field">
						<label for="bme-author">Author</label>
						<input
							id="bme-author"
							name="author"
							type="text"
							class="edit-author"
							bind:value={author}
							required
							autocomplete="off"
						/>
					</div>
					<div class="field">
						<label for="bme-isbn">ISBN</label>
						<input
							id="bme-isbn"
							name="isbn"
							type="text"
							class="edit-isbn"
							bind:value={isbn}
							autocomplete="off"
						/>
					</div>
					<div class="field">
						<label for="bme-pubdate">Publication date</label>
						<input
							id="bme-pubdate"
							name="pubdate"
							type="date"
							class="edit-pubdate"
							bind:value={pubdate}
						/>
					</div>
					<div class="field">
						<label for="bme-description">Description</label>
						<textarea
							id="bme-description"
							name="description"
							class="edit-description"
							rows="4"
							bind:value={description}
						></textarea>
					</div>
					<div class="field">
						<label for="bme-keywords">Keywords</label>
						{#if keywords.length > 0}
							<ul class="tokens" aria-label="Current keywords">
								{#each keywords as kw, i (kw)}
									<li class="token">
										<span>{kw}</span>
										<button
											type="button"
											class="kw-remove"
											data-keyword={kw}
											aria-label={`Remove keyword ${kw}`}
											onclick={() => removeKeyword(i)}
										>
											×
										</button>
									</li>
								{/each}
							</ul>
						{/if}
						<input
							id="bme-keywords"
							name="keywords"
							type="text"
							class="kw-input"
							placeholder="Add keywords, separated by commas"
							bind:value={keywordInput}
							autocomplete="off"
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ',') {
									e.preventDefault();
									commitKeywordInput();
								}
							}}
							onblur={commitKeywordInput}
						/>
					</div>
					{#if !valid}
						<p class="err" role="alert">Title and author are required.</p>
					{/if}
					{#if error}
						<p class="err server-error" role="alert">{error}</p>
					{/if}
					<div class="row">
						<button type="button" class="btn ghost edit-cancel" onclick={closeForm}>Cancel</button>
						<button
							type="submit"
							class="btn primary edit-save"
							disabled={!valid || saving}
							aria-busy={saving}
						>
							{saving ? 'Saving…' : 'Save'}
						</button>
					</div>
				</form>
			</div>
		</div>
	{/if}
</section>

<style>
	.editor {
		min-width: 0;
	}
	.btn {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		padding: 0.7rem 1rem;
		border-radius: 3px;
		text-align: center;
		cursor: pointer;
		border: 1px solid transparent;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.btn.primary {
		background: var(--ink);
		color: var(--bg);
	}
	.btn.primary:hover:not(:disabled) {
		background: var(--ink-deep);
	}
	.btn.primary:disabled {
		cursor: default;
		background: transparent;
		color: var(--muted);
		border-color: var(--line-strong);
	}
	.btn.ghost {
		background: transparent;
		color: var(--ink);
		border-color: var(--line-strong);
	}
	.btn.ghost:hover {
		border-color: var(--accent);
		color: var(--accent-deep);
	}
	.btn .ar {
		font-weight: 400;
		/* Same fixed box as the book action list, so the pencil sits on the
		   same vertical line as the other trailing icons. */
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.25em;
		line-height: 1;
	}
	/* The closed action sits in the book action list: full-width row with a
	   trailing icon, like the other actions. */
	.edit-open {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: space-between;
		text-align: center;
	}
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 60;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: rgba(20, 20, 19, 0.45);
		animation: fade 0.18s var(--ease-out) both;
	}
	.panel {
		width: min(40rem, 100%);
		max-height: calc(100dvh - 2rem);
		overflow-y: auto;
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 6px;
		box-shadow: 0 24px 60px rgba(20, 20, 19, 0.22);
		animation: fadeUp 0.24s var(--ease-out) both;
	}
	/* Scrim fades in without moving — keep entrance motion on the panel only. */
	@keyframes fade {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}
	header {
		padding: 1.5rem 1.75rem 1.25rem;
		border-bottom: var(--border);
	}
	header h2 {
		margin: 0;
		font-family: var(--f-serif);
		font-weight: 600;
		font-size: 1.5rem;
		letter-spacing: -0.01em;
		color: var(--ink);
	}
	.form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
		padding: 1.5rem 1.75rem;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.field label {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}
	.field input[type='text'],
	.field input[type='date'],
	.field textarea {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background: var(--bg);
		border: 1px solid var(--line-strong);
		border-radius: 3px;
		padding: 0.55rem 0.7rem;
	}
	.field input:focus-visible,
	.field textarea:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}
	.field textarea {
		resize: vertical;
		min-height: 4.5rem;
		line-height: 1.5;
	}
	.tokens {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		list-style: none;
		margin: 0 0 0.6rem;
		padding: 0;
	}
	.token {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-family: var(--f-grotesk);
		font-size: 0.78rem;
		font-weight: 500;
		padding: 0.2rem 0.35rem 0.2rem 0.6rem;
		border-radius: 3px;
		background: var(--chip-accent);
		color: var(--chip-accent-c);
	}
	.kw-remove {
		border: none;
		background: transparent;
		color: inherit;
		font-size: 1rem;
		line-height: 1;
		padding: 0 0.2rem;
		cursor: pointer;
		border-radius: 2px;
	}
	.kw-remove:hover {
		text-decoration: underline;
	}
	.kw-remove:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}
	.err {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		color: var(--danger);
		margin: 0;
	}
	.row {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 0.25rem;
	}
	.row .btn {
		padding: 0.55rem 1.3rem;
	}
	@media (max-width: 760px) {
		header,
		.form {
			padding-left: 1.25rem;
			padding-right: 1.25rem;
		}
		header h2 {
			font-size: 1.3rem;
		}
	}
</style>
