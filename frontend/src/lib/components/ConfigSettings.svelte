<script module lang="ts">
	import type { AiProvider, ConfigUpdate } from '$lib/api/config';

	export type ConfigSettingsConfig = {
		aiProvider: AiProvider | null;
		apiKeySet: boolean;
		rateLimit: number;
		providers: { name: AiProvider; requiresApiKey: boolean }[];
	};

	export type ConfigSettingsProps = {
		config: ConfigSettingsConfig;
		/** Injected by the route (wired to PATCH /api/config); awaited to drive
		 *  saving → saved, or → error if it rejects. Kept network-free for isolation. */
		onSave?: (patch: ConfigUpdate) => Promise<void> | void;
	};

	type State = 'idle' | 'saving' | 'saved' | 'error';
	// What to do with the API key on save: leave it, set/rotate it, or clear it.
	type KeyMode = 'keep' | 'set' | 'clear';
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';
	import { preference, setPreference, type ThemePref } from '$lib/theme';

	let { config, onSave }: ConfigSettingsProps = $props();

	let saveState = $state<State>('idle');
	// '' means no provider selected (maps to null on the wire). Seeded from the config
	// by the effect below — on mount and again after a save re-reads it.
	let providerValue = $state('');
	let rateLimit = $state(0);
	let keyMode = $state<KeyMode>('keep');
	let keyInput = $state('');
	let timer: ReturnType<typeof setTimeout> | undefined;

	// Seed (and re-seed) the editable fields from the persisted config — on mount and
	// again after a successful save, when the route passes the refreshed config back in.
	$effect(() => {
		providerValue = config.aiProvider ?? '';
		rateLimit = config.rateLimit;
		keyMode = config.apiKeySet ? 'keep' : 'set';
		keyInput = '';
	});

	let selectedProvider = $derived(config.providers.find((p) => p.name === providerValue));
	// The key field only matters for a provider that needs a key (STUB / none don't).
	let showKeyField = $derived(!!selectedProvider && selectedProvider.requiresApiKey);
	let keyAction = $derived(showKeyField ? keyMode : 'na');

	let providerChanged = $derived((providerValue || null) !== config.aiProvider);
	let rateChanged = $derived(Number.isFinite(rateLimit) && rateLimit !== config.rateLimit);
	let keyChanged = $derived(
		showKeyField && ((keyMode === 'set' && keyInput.length > 0) || keyMode === 'clear')
	);
	let dirty = $derived(providerChanged || rateChanged || keyChanged);

	let saveLabel = $derived(
		saveState === 'saving'
			? 'Saving…'
			: saveState === 'saved'
				? 'Saved'
				: saveState === 'error'
					? "Couldn't save — try again"
					: 'Save changes'
	);

	function buildPatch(): ConfigUpdate {
		const patch: ConfigUpdate = {};
		if (providerChanged) patch.ai_provider = (providerValue || null) as AiProvider | null;
		if (rateChanged) patch.extraction_rate_limit_per_minute = rateLimit;
		if (showKeyField) {
			if (keyMode === 'set' && keyInput.length > 0) patch.api_key = keyInput;
			else if (keyMode === 'clear') patch.api_key = '';
		}
		return patch;
	}

	async function save() {
		if (saveState === 'saving' || !dirty) return;
		clearTimeout(timer);
		saveState = 'saving';
		try {
			await onSave?.(buildPatch());
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
	data-verify-provider={providerValue || 'none'}
	data-verify-key-set={String(config.apiKeySet)}
	data-verify-key-action={keyAction}
	data-verify-dirty={String(dirty)}
	onsubmit={(e) => {
		e.preventDefault();
		save();
	}}
>
	<div class="field">
		<label class="label" for="ai-provider">AI provider</label>
		<div class="control">
			<select id="ai-provider" bind:value={providerValue}>
				<option value="">— None —</option>
				{#each config.providers as provider (provider.name)}
					<option value={provider.name}>{provider.name}</option>
				{/each}
			</select>
		</div>
	</div>

	<div class="field">
		<label class="label" for="api-key">API key</label>
		<div class="control">
			{#if !showKeyField}
				<p class="hint">
					{providerValue
						? `${providerValue} needs no API key.`
						: 'Select a provider to configure its API key.'}
				</p>
			{:else if config.apiKeySet && keyMode === 'keep'}
				<span class="key-status">•••• set</span>
				<button class="link key-replace" type="button" onclick={() => (keyMode = 'set')}>
					Replace
				</button>
				<button class="link key-clear" type="button" onclick={() => (keyMode = 'clear')}>
					Clear
				</button>
			{:else if keyMode === 'clear'}
				<span class="key-status">Will be cleared on save</span>
				<button class="link key-undo" type="button" onclick={() => (keyMode = 'keep')}>Undo</button>
			{:else}
				<input
					id="api-key"
					type="password"
					autocomplete="off"
					placeholder="Paste API key"
					bind:value={keyInput}
				/>
				{#if config.apiKeySet}
					<button
						class="link key-cancel"
						type="button"
						onclick={() => {
							keyMode = 'keep';
							keyInput = '';
						}}>Cancel</button
					>
				{/if}
			{/if}
		</div>
	</div>

	<div class="field">
		<label class="label" for="rate-limit">Rate limit</label>
		<div class="control">
			<input id="rate-limit" type="number" min="1" bind:value={rateLimit} />
			<span class="suffix mono">requests / minute</span>
		</div>
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

	<div class="actions">
		<button
			class="save"
			class:saved={saveState === 'saved'}
			class:error={saveState === 'error'}
			type="button"
			aria-busy={saveState === 'saving'}
			disabled={saveState === 'saving' || !dirty}
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
	input {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 3px;
		padding: 0.5rem 0.65rem;
	}
	select {
		min-width: 12rem;
	}
	input[type='number'] {
		width: 7rem;
	}
	input[type='password'] {
		min-width: 16rem;
	}
	.suffix {
		color: var(--muted);
	}
	.key-status {
		font-family: var(--f-mono);
		font-size: 0.8rem;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	.hint {
		margin: 0;
		font-family: var(--f-serif);
		color: var(--muted);
	}
	.link {
		font-family: var(--f-grotesk);
		font-size: 0.8rem;
		color: var(--accent-deep);
		background: none;
		border: none;
		padding: 0;
		text-decoration: underline;
		text-underline-offset: 2px;
		cursor: pointer;
	}
	.link:hover {
		color: var(--ink);
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
		color: var(--accent-deep);
		border-color: var(--accent-deep);
	}
	@media (max-width: 760px) {
		.field {
			grid-template-columns: 1fr;
			gap: 0.5rem;
		}
	}
</style>
