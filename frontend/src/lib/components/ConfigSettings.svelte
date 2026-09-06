<script module lang="ts">
	import type { AiProvider, ConfigUpdate } from '$lib/api/config';

	export type ConfigSettingsConfig = {
		isAdmin?: boolean;
		userInstructions?: string | null;
		extractionProvider?: AiProvider | null;
		extractionApiKeySet?: boolean;
		assistantProvider?: AiProvider | null;
		assistantApiKeySet?: boolean;
		enrichmentStage1Provider?: AiProvider | null;
		enrichmentStage1ApiKeySet?: boolean;
		enrichmentStage2Provider?: AiProvider | null;
		enrichmentStage2ApiKeySet?: boolean;
		rateLimit?: number;
		providers?: { name: AiProvider; requiresApiKey: boolean }[];
	};

	export type ConfigSettingsProps = {
		config: ConfigSettingsConfig;
		onSave?: (patch: ConfigUpdate) => Promise<void> | void;
		onSaveUserInstructions?: (instructions: string | null) => Promise<void> | void;
	};

	type State = 'idle' | 'saving' | 'saved' | 'error';
	type KeyMode = 'keep' | 'set' | 'clear';
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
	let extractionProviderValue = $state('');
	let assistantProviderValue = $state('');
	let enrichmentStage1ProviderValue = $state('');
	let enrichmentStage2ProviderValue = $state('');
	let rateLimit = $state(0);
	let extractionKeyMode = $state<KeyMode>('keep');
	let assistantKeyMode = $state<KeyMode>('keep');
	let enrichmentStage1KeyMode = $state<KeyMode>('keep');
	let enrichmentStage2KeyMode = $state<KeyMode>('keep');
	let extractionKeyInput = $state('');
	let assistantKeyInput = $state('');
	let enrichmentStage1KeyInput = $state('');
	let enrichmentStage2KeyInput = $state('');
	let userInstructionsInput = $state('');
	let timer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		extractionProviderValue = config.extractionProvider ?? '';
		assistantProviderValue = config.assistantProvider ?? '';
		enrichmentStage1ProviderValue = config.enrichmentStage1Provider ?? '';
		enrichmentStage2ProviderValue = config.enrichmentStage2Provider ?? '';
		rateLimit = config.rateLimit ?? 0;
		extractionKeyMode = config.extractionApiKeySet ? 'keep' : 'set';
		assistantKeyMode = config.assistantApiKeySet ? 'keep' : 'set';
		enrichmentStage1KeyMode = config.enrichmentStage1ApiKeySet ? 'keep' : 'set';
		enrichmentStage2KeyMode = config.enrichmentStage2ApiKeySet ? 'keep' : 'set';
		extractionKeyInput = '';
		assistantKeyInput = '';
		enrichmentStage1KeyInput = '';
		enrichmentStage2KeyInput = '';
		userInstructionsInput = config.userInstructions ?? '';
	});

	let extractionSelectedProvider = $derived(
		config.providers?.find((p) => p.name === extractionProviderValue)
	);
	let assistantSelectedProvider = $derived(
		config.providers?.find((p) => p.name === assistantProviderValue)
	);
	let enrichmentStage1SelectedProvider = $derived(
		config.providers?.find((p) => p.name === enrichmentStage1ProviderValue)
	);
	let enrichmentStage2SelectedProvider = $derived(
		config.providers?.find((p) => p.name === enrichmentStage2ProviderValue)
	);
	let showExtractionKeyField = $derived(
		!!extractionSelectedProvider && extractionSelectedProvider.requiresApiKey
	);
	let showAssistantKeyField = $derived(
		!!assistantSelectedProvider && assistantSelectedProvider.requiresApiKey
	);
	let showEnrichmentStage1KeyField = $derived(
		!!enrichmentStage1SelectedProvider && enrichmentStage1SelectedProvider.requiresApiKey
	);
	let showEnrichmentStage2KeyField = $derived(
		!!enrichmentStage2SelectedProvider && enrichmentStage2SelectedProvider.requiresApiKey
	);
	let extractionKeyAction = $derived(showExtractionKeyField ? extractionKeyMode : 'na');
	let assistantKeyAction = $derived(showAssistantKeyField ? assistantKeyMode : 'na');
	let enrichmentStage1KeyAction = $derived(
		showEnrichmentStage1KeyField ? enrichmentStage1KeyMode : 'na'
	);
	let enrichmentStage2KeyAction = $derived(
		showEnrichmentStage2KeyField ? enrichmentStage2KeyMode : 'na'
	);

	let extractionProviderChanged = $derived(
		isAdmin && (extractionProviderValue || null) !== (config.extractionProvider ?? null)
	);
	let assistantProviderChanged = $derived(
		isAdmin && (assistantProviderValue || null) !== (config.assistantProvider ?? null)
	);
	let enrichmentStage1ProviderChanged = $derived(
		isAdmin &&
			(enrichmentStage1ProviderValue || null) !== (config.enrichmentStage1Provider ?? null)
	);
	let enrichmentStage2ProviderChanged = $derived(
		isAdmin &&
			(enrichmentStage2ProviderValue || null) !== (config.enrichmentStage2Provider ?? null)
	);
	let rateChanged = $derived(
		isAdmin && Number.isFinite(rateLimit) && rateLimit !== (config.rateLimit ?? 0)
	);
	let extractionKeyChanged = $derived(
		isAdmin &&
			showExtractionKeyField &&
			((extractionKeyMode === 'set' && extractionKeyInput.length > 0) ||
				extractionKeyMode === 'clear')
	);
	let assistantKeyChanged = $derived(
		isAdmin &&
			showAssistantKeyField &&
			((assistantKeyMode === 'set' && assistantKeyInput.length > 0) ||
				assistantKeyMode === 'clear')
	);
	let enrichmentStage1KeyChanged = $derived(
		isAdmin &&
			showEnrichmentStage1KeyField &&
			((enrichmentStage1KeyMode === 'set' && enrichmentStage1KeyInput.length > 0) ||
				enrichmentStage1KeyMode === 'clear')
	);
	let enrichmentStage2KeyChanged = $derived(
		isAdmin &&
			showEnrichmentStage2KeyField &&
			((enrichmentStage2KeyMode === 'set' && enrichmentStage2KeyInput.length > 0) ||
				enrichmentStage2KeyMode === 'clear')
	);

	let normalisedInstructions = $derived(userInstructionsInput.trim() || null);
	let instructionsChanged = $derived(
		normalisedInstructions !== (config.userInstructions ?? null)
	);
	let overLimit = $derived(userInstructionsInput.length > 4000);

	let dirty = $derived(
		instructionsChanged ||
			extractionProviderChanged ||
			assistantProviderChanged ||
			enrichmentStage1ProviderChanged ||
			enrichmentStage2ProviderChanged ||
			rateChanged ||
			extractionKeyChanged ||
			assistantKeyChanged ||
			enrichmentStage1KeyChanged ||
			enrichmentStage2KeyChanged
	);

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
		if (extractionProviderChanged) {
			patch.ai_provider = (extractionProviderValue || null) as AiProvider | null;
		}
		if (assistantProviderChanged) {
			patch.assistant_provider = (assistantProviderValue || null) as AiProvider | null;
		}
		if (enrichmentStage1ProviderChanged) {
			patch.enrichment_stage1_provider = (enrichmentStage1ProviderValue || null) as
				| AiProvider
				| null;
		}
		if (enrichmentStage2ProviderChanged) {
			patch.enrichment_stage2_provider = (enrichmentStage2ProviderValue || null) as
				| AiProvider
				| null;
		}
		if (rateChanged) patch.extraction_rate_limit_per_minute = rateLimit;
		if (showExtractionKeyField) {
			if (extractionKeyMode === 'set' && extractionKeyInput.length > 0) {
				patch.api_key = extractionKeyInput;
			} else if (extractionKeyMode === 'clear') patch.api_key = '';
		}
		if (showAssistantKeyField) {
			if (assistantKeyMode === 'set' && assistantKeyInput.length > 0) {
				patch.assistant_api_key = assistantKeyInput;
			} else if (assistantKeyMode === 'clear') patch.assistant_api_key = '';
		}
		if (showEnrichmentStage1KeyField) {
			if (enrichmentStage1KeyMode === 'set' && enrichmentStage1KeyInput.length > 0) {
				patch.enrichment_stage1_api_key = enrichmentStage1KeyInput;
			} else if (enrichmentStage1KeyMode === 'clear') patch.enrichment_stage1_api_key = '';
		}
		if (showEnrichmentStage2KeyField) {
			if (enrichmentStage2KeyMode === 'set' && enrichmentStage2KeyInput.length > 0) {
				patch.enrichment_stage2_api_key = enrichmentStage2KeyInput;
			} else if (enrichmentStage2KeyMode === 'clear') patch.enrichment_stage2_api_key = '';
		}
		return patch;
	}

	async function save() {
		if (saveState === 'saving' || !dirty || overLimit) return;
		clearTimeout(timer);
		saveState = 'saving';
		try {
			const promises: Promise<void>[] = [];
			if (instructionsChanged && onSaveUserInstructions) {
				promises.push(Promise.resolve(onSaveUserInstructions(normalisedInstructions)));
			}
			if (
				isAdmin &&
				(extractionProviderChanged ||
					assistantProviderChanged ||
					enrichmentStage1ProviderChanged ||
					enrichmentStage2ProviderChanged ||
					rateChanged ||
					extractionKeyChanged ||
					assistantKeyChanged ||
					enrichmentStage1KeyChanged ||
					enrichmentStage2KeyChanged) &&
				onSave
			) {
				promises.push(Promise.resolve(onSave(buildPatch())));
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
	data-verify-extraction-provider={extractionProviderValue || 'none'}
	data-verify-extraction-key-set={String(config.extractionApiKeySet ?? false)}
	data-verify-extraction-key-action={extractionKeyAction}
	data-verify-assistant-provider={assistantProviderValue || 'none'}
	data-verify-assistant-key-set={String(config.assistantApiKeySet ?? false)}
	data-verify-assistant-key-action={assistantKeyAction}
	data-verify-enrichment-stage1-provider={enrichmentStage1ProviderValue || 'none'}
	data-verify-enrichment-stage1-key-set={String(config.enrichmentStage1ApiKeySet ?? false)}
	data-verify-enrichment-stage1-key-action={enrichmentStage1KeyAction}
	data-verify-enrichment-stage2-provider={enrichmentStage2ProviderValue || 'none'}
	data-verify-enrichment-stage2-key-set={String(config.enrichmentStage2ApiKeySet ?? false)}
	data-verify-enrichment-stage2-key-action={enrichmentStage2KeyAction}
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
			<label class="label" for="extraction-provider">Extraction provider</label>
			<div class="control">
				<select id="extraction-provider" bind:value={extractionProviderValue}>
					<option value="">— None —</option>
					{#each config.providers ?? [] as provider (provider.name)}
						<option value={provider.name}>{provider.name}</option>
					{/each}
				</select>
			</div>
		</div>

		<div class="field">
			<label class="label" for="extraction-api-key">Extraction API key</label>
			<div class="control">
				{#if !showExtractionKeyField}
					<p class="hint">
						{extractionProviderValue
							? `${extractionProviderValue} needs no API key.`
							: 'Select a provider to configure its API key.'}
					</p>
				{:else if config.extractionApiKeySet && extractionKeyMode === 'keep'}
					<span class="key-status">•••• set</span>
					<button
						class="link extraction-key-replace"
						type="button"
						onclick={() => (extractionKeyMode = 'set')}
					>
						Replace
					</button>
					<button
						class="link extraction-key-clear"
						type="button"
						onclick={() => (extractionKeyMode = 'clear')}
					>
						Clear
					</button>
				{:else if extractionKeyMode === 'clear'}
					<span class="key-status">Will be cleared on save</span>
					<button
						class="link extraction-key-undo"
						type="button"
						onclick={() => (extractionKeyMode = 'keep')}>Undo</button
					>
				{:else}
					<input
						id="extraction-api-key"
						type="password"
						autocomplete="off"
						placeholder="Paste API key"
						bind:value={extractionKeyInput}
					/>
					{#if config.extractionApiKeySet}
						<button
							class="link extraction-key-cancel"
							type="button"
							onclick={() => {
								extractionKeyMode = 'keep';
								extractionKeyInput = '';
							}}>Cancel</button
						>
					{/if}
				{/if}
			</div>
		</div>

		<div class="field">
			<label class="label" for="enrichment-stage1-provider">Ingredient parsing provider</label>
			<div class="control">
				<select id="enrichment-stage1-provider" bind:value={enrichmentStage1ProviderValue}>
					<option value="">— Use extraction provider —</option>
					{#each config.providers ?? [] as provider (provider.name)}
						<option value={provider.name}>{provider.name}</option>
					{/each}
				</select>
			</div>
		</div>

		<div class="field">
			<label class="label" for="enrichment-stage1-api-key">Ingredient parsing API key</label>
			<div class="control">
				{#if !showEnrichmentStage1KeyField}
					<p class="hint">Uses the extraction provider and API key.</p>
				{:else if config.enrichmentStage1ApiKeySet && enrichmentStage1KeyMode === 'keep'}
					<span class="key-status">•••• set</span>
					<button class="link" type="button" onclick={() => (enrichmentStage1KeyMode = 'set')}>Replace</button>
					<button class="link" type="button" onclick={() => (enrichmentStage1KeyMode = 'clear')}>Clear</button>
				{:else if enrichmentStage1KeyMode === 'clear'}
					<span class="key-status">Will be cleared on save</span>
					<button class="link" type="button" onclick={() => (enrichmentStage1KeyMode = 'keep')}>Undo</button>
				{:else}
					<input
						id="enrichment-stage1-api-key"
						type="password"
						autocomplete="off"
						placeholder="Paste API key"
						bind:value={enrichmentStage1KeyInput}
					/>
					{#if config.enrichmentStage1ApiKeySet}
						<button
							class="link"
							type="button"
							onclick={() => {
								enrichmentStage1KeyMode = 'keep';
								enrichmentStage1KeyInput = '';
							}}>Cancel</button
						>
					{/if}
				{/if}
			</div>
		</div>

		<div class="field">
			<label class="label" for="enrichment-stage2-provider">Recipe semantics and fallback provider</label>
			<div class="control">
				<select id="enrichment-stage2-provider" bind:value={enrichmentStage2ProviderValue}>
					<option value="">— Use extraction provider —</option>
					{#each config.providers ?? [] as provider (provider.name)}
						<option value={provider.name}>{provider.name}</option>
					{/each}
				</select>
			</div>
		</div>

		<div class="field">
			<label class="label" for="enrichment-stage2-api-key">Recipe semantics and fallback API key</label>
			<div class="control">
				{#if !showEnrichmentStage2KeyField}
					<p class="hint">Uses the extraction provider and API key.</p>
				{:else if config.enrichmentStage2ApiKeySet && enrichmentStage2KeyMode === 'keep'}
					<span class="key-status">•••• set</span>
					<button class="link" type="button" onclick={() => (enrichmentStage2KeyMode = 'set')}>Replace</button>
					<button class="link" type="button" onclick={() => (enrichmentStage2KeyMode = 'clear')}>Clear</button>
				{:else if enrichmentStage2KeyMode === 'clear'}
					<span class="key-status">Will be cleared on save</span>
					<button class="link" type="button" onclick={() => (enrichmentStage2KeyMode = 'keep')}>Undo</button>
				{:else}
					<input
						id="enrichment-stage2-api-key"
						type="password"
						autocomplete="off"
						placeholder="Paste API key"
						bind:value={enrichmentStage2KeyInput}
					/>
					{#if config.enrichmentStage2ApiKeySet}
						<button
							class="link"
							type="button"
							onclick={() => {
								enrichmentStage2KeyMode = 'keep';
								enrichmentStage2KeyInput = '';
							}}>Cancel</button
						>
					{/if}
				{/if}
			</div>
		</div>

		<div class="field">
			<label class="label" for="assistant-provider">Assistant provider</label>
			<div class="control">
				<select id="assistant-provider" bind:value={assistantProviderValue}>
					<option value="">— None —</option>
					{#each config.providers ?? [] as provider (provider.name)}
						<option value={provider.name}>{provider.name}</option>
					{/each}
				</select>
			</div>
		</div>

		<div class="field">
			<label class="label" for="assistant-api-key">Assistant API key</label>
			<div class="control">
				{#if !showAssistantKeyField}
					<p class="hint">
						{assistantProviderValue
							? `${assistantProviderValue} needs no API key.`
							: 'Select a provider to configure its API key.'}
					</p>
				{:else if config.assistantApiKeySet && assistantKeyMode === 'keep'}
					<span class="key-status">•••• set</span>
					<button
						class="link assistant-key-replace"
						type="button"
						onclick={() => (assistantKeyMode = 'set')}
					>
						Replace
					</button>
					<button
						class="link assistant-key-clear"
						type="button"
						onclick={() => (assistantKeyMode = 'clear')}
					>
						Clear
					</button>
				{:else if assistantKeyMode === 'clear'}
					<span class="key-status">Will be cleared on save</span>
					<button
						class="link assistant-key-undo"
						type="button"
						onclick={() => (assistantKeyMode = 'keep')}>Undo</button
					>
				{:else}
					<input
						id="assistant-api-key"
						type="password"
						autocomplete="off"
						placeholder="Paste API key"
						bind:value={assistantKeyInput}
					/>
					{#if config.assistantApiKeySet}
						<button
							class="link assistant-key-cancel"
							type="button"
							onclick={() => {
								assistantKeyMode = 'keep';
								assistantKeyInput = '';
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
