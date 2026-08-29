<script module lang="ts">
	export type ThreadPart = { type: string; [key: string]: unknown };

	export type ThreadMessage = {
		id: string;
		role: 'system' | 'user' | 'assistant';
		parts: ThreadPart[];
	};

	export type AssistantThreadProps = {
		messages: ThreadMessage[];
		/** Mirrors the Vercel AI SDK's chat status. */
		status?: 'ready' | 'submitted' | 'streaming' | 'error';
		/** The backend answered 409 — no AI provider is configured. */
		unavailable?: boolean;
		error?: string | null;
		onSend?: (text: string) => void;
	};
</script>

<script lang="ts">
	import { tick } from 'svelte';
	import { renderMarkdown } from '$lib/markdown';

	let {
		messages,
		status = 'ready',
		unavailable = false,
		error = null,
		onSend
	}: AssistantThreadProps = $props();

	let draft = $state('');
	let draftElement = $state<HTMLTextAreaElement>();

	let busy = $derived(status === 'submitted' || status === 'streaming');
	let toolParts = $derived(
		messages.flatMap((m) => m.parts.filter((p) => p.type.startsWith('tool-')))
	);

	function text(part: ThreadPart): string {
		return typeof part.text === 'string' ? part.text : '';
	}

	function toolName(part: ThreadPart): string {
		return part.type.replace(/^tool-/, '').replace(/_/g, ' ');
	}

	/** A one-line gist of what the model asked the tool for — the values, not the JSON. */
	function toolArgs(part: ThreadPart): string {
		const input = part.input;
		if (!input || typeof input !== 'object') return '';
		return Object.values(input as Record<string, unknown>)
			.map((v) => (Array.isArray(v) ? `${v.length} items` : String(v)))
			.join(' · ')
			.slice(0, 80);
	}

	function toolResult(part: ThreadPart): string {
		if (part.state === 'output-error') return 'failed';
		if (part.state !== 'output-available') return 'running…';
		const output = part.output;
		if (Array.isArray(output)) return `${output.length} result${output.length === 1 ? '' : 's'}`;
		return 'done';
	}

	function resizeDraft() {
		if (!draftElement) return;
		draftElement.style.height = 'auto';
		draftElement.style.height = `${draftElement.scrollHeight}px`;
	}

	async function send() {
		const question = draft.trim();
		if (!question || busy || unavailable) return;
		draft = '';
		await tick();
		resizeDraft();
		onSend?.(question);
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		send();
	}

	function onDraftKeydown(event: KeyboardEvent) {
		if (event.metaKey && event.key === 'Enter') {
			event.preventDefault();
			send();
		}
	}
</script>

<section
	class="thread"
	data-verify-unit="assistant-thread"
	data-verify-count={messages.length}
	data-verify-empty={messages.length === 0 ? 'true' : 'false'}
	data-verify-status={status}
	data-verify-streaming={busy ? 'true' : 'false'}
	data-verify-tool-parts={toolParts.length}
	data-verify-roles={messages.map((m) => m.role).join(',')}
	data-verify-unavailable={unavailable ? 'true' : 'false'}
	data-verify-error={error ?? ''}
>
	<div class="transcript">
		{#if unavailable}
			<p class="notice">
				No AI provider is set up yet, so the assistant has nothing to think with. Choose one in
				<a href="/config">Configuration</a>.
			</p>
		{:else if messages.length === 0}
			<div class="opening">
				<p class="lede">What are you cooking?</p>
				<p class="hint">
					Ask for something to make tonight, for a way round a missing ingredient, or for what a
					recipe in the library actually involves.
				</p>
			</div>
		{/if}

		{#each messages as message, index (message.id)}
			<!-- One answer arrives as several messages (the tool calls, then the text), so
			     only the first of a run is named — otherwise the speaker is announced
			     three times for a single reply. -->
			{@const opensRun = index === 0 || messages[index - 1].role !== message.role}
			<article
				class="msg"
				class:from-cook={message.role === 'user'}
				class:continues={!opensRun}
				data-verify-role={message.role}
				data-verify-opens-run={opensRun ? 'true' : 'false'}
			>
				{#if opensRun}
					<p class="label">{message.role === 'user' ? 'You' : 'Assistant'}</p>
				{/if}
				{#each message.parts as part, i (i)}
					{#if part.type === 'text'}
						{#if message.role === 'user'}
							<p class="said">{text(part)}</p>
						{:else}
							<!-- Model output: parsed as Markdown, then sanitised (see $lib/markdown). -->
							<div class="reply">{@html renderMarkdown(text(part))}</div>
						{/if}
					{:else if part.type.startsWith('tool-')}
						<p class="trace mono">
							<span class="trace-name">{toolName(part)}</span>
							{#if toolArgs(part)}<span class="trace-args">{toolArgs(part)}</span>{/if}
							<span class="trace-result">{toolResult(part)}</span>
						</p>
					{/if}
				{/each}
			</article>
		{/each}

		{#if busy}
			<p class="working label" aria-live="polite">Thinking</p>
		{/if}

		{#if error}
			<p class="notice error">{error}</p>
		{/if}
	</div>

	<form class="composer" onsubmit={submit}>
		<label class="sr-only" for="assistant-draft">Ask the assistant</label>
		<textarea
			id="assistant-draft"
			class="draft"
			rows="1"
			placeholder="Ask for something to cook…"
			disabled={unavailable}
			value={draft}
			bind:this={draftElement}
			oninput={(event) => {
				draft = event.currentTarget.value;
				resizeDraft();
			}}
			onkeydown={onDraftKeydown}
		></textarea>
		<button
			class="send"
			type="submit"
			aria-label={busy ? 'Sending message' : 'Send message'}
			disabled={busy || unavailable || draft.trim() === ''}
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M12 19V5M6 11l6-6 6 6" />
			</svg>
		</button>
	</form>
</section>

<style>
	.thread {
		display: flex;
		flex-direction: column;
		min-height: 0;
		gap: 1.5rem;
	}

	.transcript {
		display: flex;
		flex-direction: column;
		gap: 2.25rem;
		padding-bottom: 1rem;
	}

	/* A continuation of the same speaker sits close to what it continues. */
	.transcript .continues {
		margin-top: -1.5rem;
	}

	.opening {
		border-left: 2px solid var(--clay);
		padding-left: 1.25rem;
	}

	.lede {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 2rem;
		line-height: 1.15;
		margin: 0 0 0.6rem;
	}

	.hint {
		font-family: var(--f-serif);
		color: var(--muted);
		max-width: 42ch;
		margin: 0;
	}

	.msg {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}

	.msg .label {
		color: var(--faint);
	}

	.from-cook .label {
		color: var(--clay-deep);
	}

	.said {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.15rem;
		margin: 0;
		max-width: 60ch;
		overflow-wrap: anywhere;
	}

	.reply {
		font-family: var(--f-serif);
		max-width: 66ch;
		line-height: 1.6;
		overflow-wrap: anywhere;
	}

	.reply :global(p) {
		margin: 0 0 0.75rem;
	}

	.reply :global(a) {
		color: var(--clay-deep);
		text-underline-offset: 3px;
	}

	.reply :global(ul),
	.reply :global(ol) {
		margin: 0 0 0.75rem;
		padding-left: 1.25rem;
	}

	.reply :global(code) {
		font-family: var(--f-mono);
		font-size: 0.85em;
	}

	/* The tool trace: a hairline ledger line, deliberately quiet — it is evidence of
	   the search, not part of the answer. */
	.trace {
		display: flex;
		flex-wrap: wrap;
		gap: 0 0.75rem;
		align-items: baseline;
		margin: 0;
		padding: 0.35rem 0;
		border-top: var(--border);
		color: var(--faint);
		max-width: 60ch;
	}

	.trace-name {
		color: var(--muted);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-size: 0.62rem;
	}

	.trace-args {
		font-style: italic;
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.trace-result {
		margin-left: auto;
	}

	.working {
		color: var(--clay-deep);
		animation: pulse 1.4s ease-in-out infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.35;
		}
	}

	.notice {
		font-family: var(--f-serif);
		font-style: italic;
		color: var(--muted);
		background: var(--bg-warm);
		border: var(--border);
		padding: 1rem 1.25rem;
		margin: 0;
		max-width: 60ch;
	}

	.notice.error {
		border-color: var(--clay);
	}

	.composer {
		position: sticky;
		bottom: 0;
		display: flex;
		gap: 0.75rem;
		align-items: flex-end;
		background: var(--bg);
		border-top: var(--border-strong);
		padding: 1rem 0 max(1rem, env(safe-area-inset-bottom));
	}

	.draft {
		flex: 1;
		box-sizing: border-box;
		max-height: calc(100vh - 12rem);
		resize: none;
		overflow-y: auto;
		font-family: var(--f-serif);
		font-size: 1rem;
		color: var(--ink);
		background: var(--bg);
		border: var(--border);
		border-radius: 3px;
		padding: 0.7rem 0.85rem;
	}

	.draft:disabled {
		color: var(--faint);
	}

	.send {
		display: grid;
		place-items: center;
		flex: 0 0 2.8rem;
		height: 2.8rem;
		background: var(--ink);
		color: var(--bg);
		border: none;
		border-radius: 3px;
		padding: 0;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
	}

	.send svg {
		width: 1.1rem;
		height: 1.1rem;
	}

	.send:hover:not(:disabled) {
		background: var(--clay-deep);
	}

	.send:disabled {
		background: var(--faint);
		cursor: default;
	}

	@media (prefers-reduced-motion: reduce) {
		.working {
			animation: none;
		}
	}
</style>
