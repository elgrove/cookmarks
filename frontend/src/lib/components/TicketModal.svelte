<script lang="ts">
	import type { TicketInput, TicketResult } from '$lib/api/tickets';

	let {
		open = $bindable(false),
		onSubmit
	}: {
		open: boolean;
		/** Injected by the shell (wired to POST /api/tickets); awaited to drive the
		 *  submitting → filed flow. Kept network-free so the modal stays isolatable. */
		onSubmit: (input: TicketInput) => Promise<TicketResult>;
	} = $props();

	type Phase = 'editing' | 'submitting' | 'filed';

	let title = $state('');
	let description = $state('');
	let phase = $state<Phase>('editing');
	let error = $state<string | null>(null);
	let filed = $state<TicketResult | null>(null);

	// Reset the form each time the dialog is (re)opened.
	$effect(() => {
		if (open) {
			title = '';
			description = '';
			phase = 'editing';
			error = null;
			filed = null;
		}
	});

	function close() {
		open = false;
	}

	async function submit() {
		if (phase === 'submitting') return;
		const trimmed = title.trim();
		if (!trimmed) {
			error = 'Please give the ticket a title.';
			return;
		}
		phase = 'submitting';
		error = null;
		try {
			filed = await onSubmit({
				title: trimmed,
				description: description.trim(),
				page_url: typeof window !== 'undefined' ? window.location.href : null
			});
			phase = 'filed';
		} catch {
			phase = 'editing';
			error = 'Could not file the ticket. Please try again.';
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
	}
</script>

<svelte:window onkeydown={open ? onKeydown : undefined} />

{#if open}
	<div
		class="overlay"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) close();
		}}
	>
		<div class="panel" role="dialog" aria-modal="true" aria-labelledby="ticket-heading">
			{#if phase === 'filed' && filed}
				<header>
					<h2 id="ticket-heading">Thank you</h2>
				</header>
				<div class="body">
					<p class="confirm">
						Filed as
						<a href={filed.url} target="_blank" rel="noopener noreferrer">{filed.identifier}</a>.
						We'll take a look.
					</p>
					<div class="actions">
						<button class="btn-primary" type="button" onclick={close}>Done</button>
					</div>
				</div>
			{:else}
				<header>
					<h2 id="ticket-heading">Report a problem or request</h2>
				</header>
				<form
					class="body"
					onsubmit={(e) => {
						e.preventDefault();
						submit();
					}}
				>
					<div class="field">
						<label class="label" for="ticket-title">Title</label>
						<input
							id="ticket-title"
							type="text"
							placeholder="Short summary of the problem"
							bind:value={title}
							disabled={phase === 'submitting'}
						/>
					</div>
					<div class="field">
						<label class="label" for="ticket-description">Details</label>
						<textarea
							id="ticket-description"
							rows="5"
							placeholder="What happened, what you expected, and how to reproduce it"
							bind:value={description}
							disabled={phase === 'submitting'}
						></textarea>
					</div>
					{#if error}
						<p class="error" role="alert">{error}</p>
					{/if}
					<div class="actions">
						<button class="btn-ghost" type="button" onclick={close}>Cancel</button>
						<button class="btn-primary" type="submit" disabled={phase === 'submitting'}>
							{phase === 'submitting' ? 'Submitting…' : 'Submit ticket'}
						</button>
					</div>
				</form>
			{/if}
		</div>
	</div>
{/if}

<style>
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
		width: min(34rem, 100%);
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
		margin: 0.4rem 0 0;
		font-family: var(--f-serif);
		font-weight: 600;
		font-size: 1.5rem;
		letter-spacing: -0.01em;
		color: var(--ink);
	}
	.body {
		padding: 1.5rem 1.75rem;
		display: flex;
		flex-direction: column;
		gap: 1.2rem;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	input,
	textarea {
		font-family: var(--f-grotesk);
		font-size: 0.95rem;
		color: var(--ink);
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 3px;
		padding: 0.55rem 0.7rem;
		width: 100%;
	}
	textarea {
		resize: vertical;
		min-height: 6rem;
		line-height: 1.5;
	}
	input::placeholder,
	textarea::placeholder {
		color: var(--faint);
	}
	input:disabled,
	textarea:disabled {
		opacity: 0.6;
	}
	.error {
		margin: 0;
		color: var(--accent-deep);
		font-size: 0.9rem;
	}
	.confirm {
		margin: 0;
		font-family: var(--f-serif);
		font-size: 1.05rem;
		color: var(--ink);
	}
	.confirm a {
		color: var(--accent-deep);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 0.25rem;
	}
	.btn-primary,
	.btn-ghost {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		border-radius: 3px;
		padding: 0.55rem 1.3rem;
		cursor: pointer;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.btn-primary {
		color: var(--bg);
		background: var(--ink);
		border: 1px solid var(--ink);
	}
	.btn-primary:hover:not(:disabled) {
		background: var(--ink-deep);
		border-color: var(--ink-deep);
	}
	.btn-primary:disabled {
		cursor: default;
		color: var(--muted);
		background: transparent;
		border-color: var(--line-strong);
	}
	.btn-ghost {
		color: var(--ink);
		background: transparent;
		border: var(--border-strong);
	}
	.btn-ghost:hover {
		border-color: var(--ink);
	}
	@media (max-width: 760px) {
		header,
		.body {
			padding-left: 1.25rem;
			padding-right: 1.25rem;
		}
		header h2 {
			font-size: 1.3rem;
		}
	}
</style>
