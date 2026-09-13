<script module lang="ts">
	import type { ConfigUpdate } from '$lib/api/config';

	export type ConfigSettingsConfig = {
		isAdmin?: boolean;
		userInstructions?: string | null;
		rateLimit?: number;
	};

	export type ConfigSettingsProps = {
		config: ConfigSettingsConfig;
		onSave?: (patch: ConfigUpdate) => Promise<void> | void;
		onSaveUserInstructions?: (instructions: string | null) => Promise<void> | void;
	};

	type State = 'idle' | 'saving' | 'saved' | 'error';
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';
	import { preference, setPreference, type ThemePref } from '$lib/theme';
	import { currentUser, getBookGridDensity, setBookGridDensity } from '$lib/auth';
	import type { BookGridDensity } from '$lib/api/auth';

	let { config, onSave, onSaveUserInstructions }: ConfigSettingsProps = $props();

	let isAdmin = $derived(config.isAdmin ?? true);

	let saveState = $state<State>('idle');
	let density = $derived($currentUser?.book_grid_density ?? getBookGridDensity());

	function handleDensityChange(d: BookGridDensity) {
		void setBookGridDensity(d);
	}
	let rateLimit = $state(0);
	let userInstructionsInput = $state('');
	let timer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		rateLimit = config.rateLimit ?? 0;
		userInstructionsInput = config.userInstructions ?? '';
	});

	let rateChanged = $derived(
		isAdmin && Number.isFinite(rateLimit) && rateLimit !== (config.rateLimit ?? 0)
	);

	let normalisedInstructions = $derived(userInstructionsInput.trim() || null);
	let instructionsChanged = $derived(
		normalisedInstructions !== (config.userInstructions ?? null)
	);
	let overLimit = $derived(userInstructionsInput.length > 4000);

	let dirty = $derived(instructionsChanged || rateChanged);

	let saveLabel = $derived(
		saveState === 'saving'
			? 'Saving…'
			: saveState === 'saved'
				? 'Saved'
				: saveState === 'error'
					? "Couldn't save — try again"
					: 'Save changes'
	);

	async function save() {
		if (saveState === 'saving' || !dirty || overLimit) return;
		clearTimeout(timer);
		saveState = 'saving';
		try {
			const promises: Promise<void>[] = [];
			if (instructionsChanged && onSaveUserInstructions) {
				promises.push(Promise.resolve(onSaveUserInstructions(normalisedInstructions)));
			}
			if (isAdmin && rateChanged && onSave) {
				promises.push(
					Promise.resolve(onSave({ extraction_rate_limit_per_minute: rateLimit }))
				);
			}
			await Promise.all(promises);
			saveState = 'saved';
			timer = setTimeout(() => (saveState = 'idle'), 2500);
		} catch {
			saveState = 'error';
			timer = setTimeout(() => (saveState = 'idle'), 4000);
		}
	}

	onDestroy(() => clearTimeout(timer));
</script>

<form
	class="settings"
	data-verify-unit="config-settings"
	data-verify-state={saveState}
	data-verify-is-admin={String(isAdmin)}
	data-verify-user-instructions={userInstructionsInput}
	data-verify-user-instructions-action={instructionsChanged ? 'set' : 'keep'}
	data-verify-rate-limit={String(rateLimit)}
	data-verify-book-grid-density={density}
	data-verify-dirty={String(dirty)}
	data-verify-over-limit={String(overLimit)}
	onsubmit={(e) => {
		e.preventDefault();
		save();
	}}
>
	<div class="field vertical">
		<div class="field-header">
			<label class="label" for="user-instructions">User instructions</label>
			<span class="char-count" class:limit-reached={overLimit}>
				{userInstructionsInput.length.toLocaleString('en-GB')} / 4,000
			</span>
		</div>
		<p class="hint">
			Tell the assistant how you want it to help, including any kitchen, equipment, dietary
			preferences, or style notes.
		</p>
		<textarea
			id="user-instructions"
			rows="6"
			bind:value={userInstructionsInput}
			placeholder="e.g. Vegetarian. Cooking on induction with cast iron. Likes bold acid and lots of herbs. No coriander."
		></textarea>
	</div>

	<div class="field">
		<label class="label" for="appearance">Appearance</label>
		<div class="control">
			<select
				id="appearance"
				value={$preference}
				onchange={(e) => setPreference((e.currentTarget as HTMLSelectElement).value as ThemePref)}
			>
				<option value="light">Light</option>
				<option value="dark">Dark</option>
				<option value="system">System</option>
			</select>
		</div>
	</div>

	<div class="field">
		<label class="label" for="book-grid-density">Book grid density</label>
		<div class="control">
			<select
				id="book-grid-density"
				value={density}
				onchange={(e) => handleDensityChange((e.currentTarget as HTMLSelectElement).value as BookGridDensity)}
			>
				<option value="sparse">Sparse</option>
				<option value="standard">Standard</option>
				<option value="compact">Compact</option>
			</select>
		</div>
	</div>

	{#if isAdmin}
		<div class="field">
			<label class="label" for="rate-limit">Rate limit</label>
			<div class="control">
				<input id="rate-limit" type="number" min="1" bind:value={rateLimit} />
				<span class="suffix mono">requests / minute</span>
			</div>
		</div>
	{/if}

	<div class="actions">
		<button
			class="save"
			class:saved={saveState === 'saved'}
			class:error={saveState === 'error'}
			type="button"
			aria-busy={saveState === 'saving'}
			disabled={saveState === 'saving' || !dirty || overLimit}
			onclick={save}
		>
			{saveLabel}
		</button>
	</div>
</form>

<style>
	.settings {
		display: flex;
		flex-direction: column;
	}
	.field {
		display: grid;
		grid-template-columns: 10rem 1fr;
		align-items: center;
		gap: 1rem;
		padding: 1.1rem 0;
		border-bottom: var(--border);
	}
	.field.vertical {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 0.5rem;
	}
	.field-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.char-count {
		font-family: var(--f-mono);
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		color: var(--muted);
	}
	.char-count.limit-reached {
		color: var(--clay-deep);
		font-weight: 600;
	}
	.field .label {
		padding-top: 0;
	}
	.control {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.6rem 0.9rem;
	}
	select,
	input,
	textarea {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 3px;
		padding: 0.5rem 0.65rem;
	}
	textarea {
		width: 100%;
		box-sizing: border-box;
		line-height: 1.5;
		resize: vertical;
	}
	textarea:focus,
	input:focus,
	select:focus {
		border-color: var(--clay-deep);
		outline: none;
	}
	select {
		min-width: 12rem;
	}
	input[type='number'] {
		width: 7rem;
	}
	.suffix {
		color: var(--muted);
	}
	.hint {
		margin: 0;
		font-family: var(--f-serif);
		color: var(--muted);
	}
	.actions {
		margin-top: 2rem;
	}
	.save {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--bg);
		background: var(--ink);
		border: 1px solid var(--ink);
		border-radius: 3px;
		padding: 0.6rem 1.4rem;
		cursor: pointer;
		transition:
			background 0.18s var(--ease-out),
			border-color 0.18s var(--ease-out);
	}
	.save:hover:not(:disabled) {
		background: var(--ink-deep);
		border-color: var(--ink-deep);
	}
	.save:disabled {
		cursor: default;
		color: var(--muted);
		background: transparent;
		border-color: var(--line-strong);
	}
	.save.saved {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--bg);
	}
	.save.error {
		background: transparent;
		color: var(--danger);
		border-color: var(--danger);
	}
	@media (max-width: 760px) {
		.field {
			grid-template-columns: 1fr;
			gap: 0.5rem;
		}
	}
</style>
