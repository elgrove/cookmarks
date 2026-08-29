<script module lang="ts">
	export type AccountSettingsProps = {
		username: string;
		instructions: string | null;
		onSave?: (instructions: string | null) => Promise<void> | void;
	};

	type State = 'idle' | 'saving' | 'saved' | 'error';
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';

	let { username, instructions, onSave }: AccountSettingsProps = $props();

	let saveState = $state<State>('idle');
	let errorMessage = $state('');
	let instructionsInput = $state('');
	let timer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		instructionsInput = instructions ?? '';
	});

	let normalised = $derived(instructionsInput.trim() || null);
	let dirty = $derived(normalised !== (instructions ?? null));
	let overLimit = $derived(instructionsInput.length > 4000);

	let saveLabel = $derived(
		saveState === 'saving'
			? 'Saving…'
			: saveState === 'saved'
				? 'Saved'
				: saveState === 'error'
					? "Couldn't save — try again"
					: 'Save instructions'
	);

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (!dirty || overLimit || saveState === 'saving') return;

		clearTimeout(timer);
		saveState = 'saving';
		errorMessage = '';

		try {
			await onSave?.(normalised);
			saveState = 'saved';
			timer = setTimeout(() => {
				if (saveState === 'saved') saveState = 'idle';
			}, 3000);
		} catch (err) {
			saveState = 'error';
			errorMessage = err instanceof Error ? err.message : "Couldn't save instructions.";
		}
	}

	onDestroy(() => clearTimeout(timer));
</script>

<div
	class="account-settings"
	data-verify-unit="account-settings"
	data-verify-state={saveState}
	data-verify-dirty={dirty ? 'true' : 'false'}
	data-verify-length={instructionsInput.length}
	data-verify-over-limit={overLimit ? 'true' : 'false'}
	data-verify-error={errorMessage}
>
	<header class="account-header">
		<div class="account-meta">
			<span class="label">Account</span>
			<h1 class="account-title">{username}</h1>
		</div>
	</header>

	<form class="account-form" onsubmit={handleSubmit}>
		<section class="section">
			<div class="section-head">
				<span class="sec-num">01</span>
				<h2 class="sec-title">Personal cooking instructions</h2>
			</div>

			<p class="section-desc">
				Tell the assistant about your kitchen, equipment, pantry staples, dietary preferences, or
				cooking style. These notes guide the assistant across every conversation.
			</p>

			<div class="field">
				<div class="field-header">
					<label class="field-label" for="cooking-instructions">Instructions</label>
					<span class="char-count" class:limit-reached={overLimit}>
						{instructionsInput.length.toLocaleString('en-GB')} / 4,000
					</span>
				</div>
				<textarea
					id="cooking-instructions"
					name="cooking_instructions"
					rows="8"
					bind:value={instructionsInput}
					placeholder="e.g. Vegetarian. Cooking on induction with cast iron. Likes bold acid and lots of herbs. No coriander."
				></textarea>
			</div>

			{#if saveState === 'error' && errorMessage}
				<p class="error-text" role="alert">{errorMessage}</p>
			{/if}

			<div class="actions">
				<button
					type="submit"
					class="save-button"
					disabled={!dirty || overLimit || saveState === 'saving'}
				>
					{saveLabel}
				</button>
			</div>
		</section>
	</form>
</div>

<style>
	.account-settings {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 2rem var(--page-h);
	}

	.account-header {
		margin-bottom: 2.5rem;
		padding-bottom: 1.5rem;
		border-bottom: var(--rule);
	}

	.account-meta .label {
		display: block;
		font-family: var(--f-mono);
		font-size: 0.68rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--muted);
		margin-bottom: 0.25rem;
	}

	.account-title {
		font-family: var(--f-grotesk);
		font-size: 2rem;
		font-weight: 700;
		letter-spacing: -0.02em;
		color: var(--ink);
		margin: 0;
	}

	.account-form {
		display: flex;
		flex-direction: column;
		gap: 2rem;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.section-head {
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		border-bottom: var(--border-strong);
		padding-bottom: 0.5rem;
	}

	.sec-num {
		font-family: var(--f-mono);
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--accent);
	}

	.sec-title {
		font-family: var(--f-grotesk);
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--ink);
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.section-desc {
		font-family: var(--f-grotesk);
		font-size: 0.95rem;
		color: var(--muted);
		line-height: 1.5;
		margin: 0;
		max-width: 65ch;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.field-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}

	.field-label {
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.char-count {
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.08em;
		color: var(--faint);
	}

	.char-count.limit-reached {
		color: var(--clay-deep, #b91c1c);
		font-weight: 600;
	}

	textarea {
		font-family: var(--f-grotesk);
		font-size: 0.95rem;
		line-height: 1.5;
		color: var(--ink);
		background: var(--card);
		border: 1px solid var(--ink);
		padding: 0.875rem 1rem;
		box-sizing: border-box;
		width: 100%;
		resize: vertical;
		outline: none;
	}

	textarea:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 1px var(--accent);
	}

	.error-text {
		font-family: var(--f-mono);
		font-size: 0.78rem;
		color: var(--clay-deep, #b91c1c);
		margin: 0;
	}

	.actions {
		display: flex;
		justify-content: flex-start;
		margin-top: 0.5rem;
	}

	.save-button {
		font-family: var(--f-mono);
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		padding: 0.65rem 1.25rem;
		background: var(--accent);
		color: #ffffff;
		border: 1px solid var(--accent);
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.save-button:hover:not(:disabled) {
		background: var(--accent-deep);
		border-color: var(--accent-deep);
	}

	.save-button:disabled {
		background: var(--card);
		color: var(--faint);
		border-color: var(--line-strong);
		cursor: not-allowed;
	}

	@media (max-width: 768px) {
		.account-settings {
			padding: 1.5rem 1rem;
		}
	}
</style>
