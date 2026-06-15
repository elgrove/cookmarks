<script module lang="ts">
	import type { ReviewQuestion } from '$lib/api/task-runs';

	export type ReviewPromptProps = {
		/** The pending question on a run paused at REVIEW, or null when nothing awaits an
		 *  answer — the component renders an inert "none" state in that case. */
		review?: ReviewQuestion | null;
		/** Injected so the component stays network-free and verifiable in isolation; the
		 *  page wires this to the resume POST. Awaited to drive submitting → submitted. */
		onAnswer?: (value: string) => Promise<void> | void;
	};

	type Phase = 'idle' | 'submitting' | 'submitted' | 'error';
</script>

<script lang="ts">
	let { review = null, onAnswer }: ReviewPromptProps = $props();

	let phase = $state<Phase>('idle');

	// 'none' isn't a phase the operator can act in — it's the absence of a question.
	let displayState = $derived(review ? phase : 'none');
	let choiceCount = $derived(review ? review.choices.length : 0);

	async function answer(value: string) {
		if (phase === 'submitting' || phase === 'submitted') return;
		phase = 'submitting';
		try {
			await onAnswer?.(value);
			phase = 'submitted';
		} catch {
			phase = 'error';
		}
	}
</script>

<section
	class="review"
	class:done={displayState === 'submitted'}
	role="group"
	aria-label={review ? review.question : 'No extraction review pending'}
	data-verify-unit="review-prompt"
	data-verify-state={displayState}
	data-verify-choice-count={choiceCount}
	data-verify-pending={review ? 'true' : 'false'}
>
	{#if review}
		<p class="eyebrow">Extraction paused</p>
		<p class="question">{review.question}</p>

		{#if displayState === 'submitted'}
			<p class="resolved">Answer sent — resuming extraction…</p>
		{:else}
			<div class="choices">
				{#each review.choices as choice (choice.value)}
					<button
						type="button"
						class="choice"
						data-choice={choice.value}
						disabled={displayState === 'submitting'}
						onclick={() => answer(choice.value)}
					>
						{choice.label}
					</button>
				{/each}
			</div>
			{#if displayState === 'error'}
				<p class="err" role="alert">Couldn't send your answer — try again.</p>
			{/if}
		{/if}
	{/if}
</section>

<style>
	.review {
		border: 1px solid var(--clay);
		border-left: 3px solid var(--clay);
		border-radius: 3px;
		background: var(--bg-warm);
		padding: 1.1rem 1.3rem;
	}
	/* The inert "no pending question" state has nothing to show. */
	.review:empty {
		display: none;
	}
	.eyebrow {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--clay-deep);
		margin: 0 0 0.4rem;
	}
	.question {
		font-family: var(--f-serif);
		font-size: 1.15rem;
		line-height: 1.4;
		color: var(--ink);
		margin: 0 0 0.9rem;
	}
	.choices {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
	}
	.choice {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		padding: 0.55rem 1rem;
		border-radius: 3px;
		background: transparent;
		color: var(--clay-deep);
		border: 1px solid var(--clay);
		cursor: pointer;
		transition:
			background 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.choice:hover:not(:disabled) {
		background: var(--clay);
		color: var(--bg);
	}
	.choice:disabled {
		cursor: default;
		color: var(--muted);
		border-color: var(--line-strong);
	}
	.resolved {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--clay-deep);
		margin: 0;
	}
	.err {
		font-family: var(--f-grotesk);
		font-size: 0.8rem;
		color: var(--clay-deep);
		margin: 0.7rem 0 0;
	}
</style>
