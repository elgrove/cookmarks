<script module lang="ts">
	import type {
		AiProvider,
		AiReadiness,
		Config,
		ConfigUpdate,
		ModelRole
	} from '$lib/api/config';

	export type AIConfigurationProps = {
		config: Config;
		readiness: AiReadiness | null;
		isAdmin?: boolean;
		onSave?: (patch: ConfigUpdate) => Promise<void> | void;
	};

	type State = 'idle' | 'saving' | 'saved' | 'error';
	type KeyMode = 'keep' | 'set' | 'clear';
	type Selection = { provider: AiProvider; model: string } | null;

	const ROLE_LABELS: Record<ModelRole, string> = {
		image_match: 'Image matching',
		ocr: 'PDF text recognition',
		many_recipes_per_file: 'File extraction, many recipes',
		one_recipe_per_file: 'File extraction, one recipe',
		blocks_of_files: 'Block extraction',
		book_keywords: 'Book keywords',
		keyword_classification: 'Keyword classification',
		keyword_dedup: 'Keyword clean-up',
		ingredient_dedup: 'Ingredient clean-up',
		assistant: 'Assistant chat',
		recipe_enrichment: 'Recipe enrichment',
		recipe_ingredients: 'Ingredient parsing',
		recipe_ingredients_fallback: 'Ingredient fallback',
		recipe_semantics: 'Recipe semantics'
	};

	const GROUPS: { title: string; roles: ModelRole[] }[] = [
		{
			title: 'Extraction',
			roles: [
				'image_match',
				'many_recipes_per_file',
				'one_recipe_per_file',
				'blocks_of_files',
				'ocr'
			]
		},
		{
			title: 'Recipe enrichment',
			roles: ['recipe_ingredients', 'recipe_semantics', 'recipe_enrichment']
		},
		{
			title: 'Library',
			roles: ['book_keywords', 'keyword_classification', 'keyword_dedup', 'ingredient_dedup']
		},
		{ title: 'Assistant', roles: ['assistant'] }
	];

	// Fixed order for the verify contract's assignment string.
	const ROLE_ORDER: ModelRole[] = GROUPS.flatMap((g) => g.roles);
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';

	let { config, readiness, isAdmin = true, onSave }: AIConfigurationProps = $props();

	let saveState = $state<State>('idle');
	let timer: ReturnType<typeof setTimeout> | undefined;

	let order = $state<AiProvider[]>([]);
	let keyModes = $state<Record<string, KeyMode>>({});
	let keyInputs = $state<Record<string, string>>({});
	let modelLists = $state<Record<string, string[]>>({});
	let newModelInputs = $state<Record<string, string>>({});
	let selections = $state<Record<string, Selection>>({});
	let chain = $state<{ provider: AiProvider; model: string }[]>([]);
	let chainProvider = $state<AiProvider | ''>('');
	let chainModel = $state('');
	let originalChain = $state<{ provider: AiProvider; model: string }[]>([]);

	$effect(() => {
		const providers = [...config.providers].sort((a, b) => a.display_order - b.display_order);
		order = providers.map((p) => p.provider);
		keyModes = Object.fromEntries(providers.map((p) => [p.provider, p.api_key_set ? 'keep' : 'set']));
		keyInputs = Object.fromEntries(providers.map((p) => [p.provider, '']));
		modelLists = Object.fromEntries(providers.map((p) => [p.provider, [...p.model_ids]]));
		newModelInputs = Object.fromEntries(providers.map((p) => [p.provider, '']));
		const byRole = new Map<string, { provider: AiProvider; model: string }[]>();
		for (const a of config.task_assignments) {
			const list = byRole.get(a.role) ?? [];
			list.push({ provider: a.provider, model: a.model_id });
			byRole.set(a.role, list);
		}
		const next: Record<string, Selection> = {};
		for (const group of GROUPS) {
			for (const role of group.roles) {
				if (role === 'recipe_ingredients') continue;
				const list = byRole.get(role) ?? [];
				next[role] = list[0] ?? null;
			}
		}
		selections = next;
		const nextChain = [...(byRole.get('recipe_ingredients') ?? [])];
		chain = nextChain;
		originalChain = [...nextChain];
		chainProvider = '';
		chainModel = '';
	});

	let originalOrder = $derived(
		[...config.providers].sort((a, b) => a.display_order - b.display_order).map((p) => p.provider)
	);
	let originalModels = $derived(
		Object.fromEntries(config.providers.map((p) => [p.provider, [...p.model_ids]]))
	);
	let originalSelections = $derived.by(() => {
		const byRole = new Map<string, { provider: AiProvider; model: string }[]>();
		for (const a of config.task_assignments) {
			const list = byRole.get(a.role) ?? [];
			list.push({ provider: a.provider, model: a.model_id });
			byRole.set(a.role, list);
		}
		return byRole;
	});

	let orderChanged = $derived(
		isAdmin &&
			(order.length !== originalOrder.length ||
				order.some((p, i) => p !== originalOrder[i]))
	);
	let keysChanged = $derived(
		isAdmin &&
			order.some((p) => {
				const mode = keyModes[p];
				if (mode === 'clear') return true;
				if (mode === 'set' && (keyInputs[p] ?? '').trim().length > 0) return true;
				return false;
			})
	);
	let modelsChanged = $derived(
		isAdmin &&
			order.some((p) => {
				const current = modelLists[p] ?? [];
				const original = originalModels[p] ?? [];
				return (
					current.length !== original.length || current.some((m, i) => m !== original[i])
				);
			})
	);
	let tasksChanged = $derived(
		isAdmin &&
			ROLE_ORDER.some((role) => {
				if (role === 'recipe_ingredients') {
					if (chain.length !== originalChain.length) return true;
					return chain.some(
						(e, i) =>
							e.provider !== originalChain[i]?.provider || e.model !== originalChain[i]?.model
					);
				}
				const current = selections[role] ?? null;
				const original = originalSelections.get(role)?.[0] ?? null;
				if (current === null || original === null) return current !== original;
				return current.provider !== original.provider || current.model !== original.model;
			})
	);

	let dirty = $derived(orderChanged || keysChanged || modelsChanged || tasksChanged);

	let saveLabel = $derived(
		saveState === 'saving'
			? 'Saving…'
			: saveState === 'saved'
				? 'Saved'
				: saveState === 'error'
					? "Couldn't save — try again"
					: 'Save changes'
	);

	let setupState = $derived(
		readiness === null ? 'unknown' : readiness.extraction_available ? 'ready' : 'setup-required'
	);

	let providerOrderText = $derived(order.join(','));
	let modelCountsText = $derived(order.map((p) => `${p}:${(modelLists[p] ?? []).length}`).join(','));
	let assignmentsText = $derived(
		ROLE_ORDER.flatMap((role) => {
			if (role === 'recipe_ingredients') {
				if (chain.length === 0) return [];
				return [`${role}=${chain.map((e) => `${e.provider}:${e.model}`).join('+')}`];
			}
			const sel = selections[role] ?? null;
			if (sel === null) return [];
			return [`${role}=${sel.provider}:${sel.model}`];
		}).join(';')
	);
	let fallbackOrderText = $derived(
		chain.length === 0 ? 'none' : chain.map((e) => e.provider).join(',')
	);

	function referencedModels(provider: AiProvider): Set<string> {
		const used = new Set<string>();
		for (const role of ROLE_ORDER) {
			if (role === 'recipe_ingredients') {
				for (const e of chain) if (e.provider === provider) used.add(e.model);
			} else {
				const sel = selections[role] ?? null;
				if (sel !== null && sel.provider === provider) used.add(sel.model);
			}
		}
		return used;
	}

	function recommendation(role: ModelRole, provider: AiProvider): string | null {
		return config.recommendations[provider]?.[role] ?? null;
	}

	function moveProvider(provider: AiProvider, delta: -1 | 1) {
		const i = order.indexOf(provider);
		const j = i + delta;
		if (i < 0 || j < 0 || j >= order.length) return;
		const next = [...order];
		[next[i], next[j]] = [next[j], next[i]];
		order = next;
	}

	function addModel(provider: AiProvider) {
		const name = (newModelInputs[provider] ?? '').trim();
		if (!name) return;
		const list = modelLists[provider] ?? [];
		if (list.includes(name)) return;
		modelLists = { ...modelLists, [provider]: [...list, name] };
		newModelInputs = { ...newModelInputs, [provider]: '' };
	}

	function removeModel(provider: AiProvider, model: string) {
		if (referencedModels(provider).has(model)) return;
		modelLists = {
			...modelLists,
			[provider]: (modelLists[provider] ?? []).filter((m) => m !== model)
		};
	}

	function selectTaskProvider(role: ModelRole, provider: AiProvider | '') {
		if (provider === '') {
			selections = { ...selections, [role]: null };
			return;
		}
		const list = modelLists[provider] ?? [];
		const current = selections[role] ?? null;
		// Keep the current model when still listed; otherwise prefer the provider's
		// recommendation over the list's first entry.
		const recommended = recommendation(role, provider);
		const model =
			current !== null && current.provider === provider && list.includes(current.model)
				? current.model
				: recommended !== null && list.includes(recommended)
					? recommended
					: (list[0] ?? '');
		selections = { ...selections, [role]: { provider, model } };
	}

	function selectTaskModel(role: ModelRole, model: string) {
		const current = selections[role] ?? null;
		if (current === null) return;
		selections = { ...selections, [role]: { ...current, model } };
	}

	function chainModels(): string[] {
		if (chainProvider === '') return [];
		return modelLists[chainProvider] ?? [];
	}

	function addChainEntry() {
		if (chainProvider === '' || chainModel === '') return;
		chain = [...chain, { provider: chainProvider, model: chainModel }];
		chainProvider = '';
		chainModel = '';
	}

	function moveChainEntry(index: number, delta: -1 | 1) {
		const j = index + delta;
		if (j < 0 || j >= chain.length) return;
		const next = [...chain];
		[next[index], next[j]] = [next[j], next[index]];
		chain = next;
	}

	function removeChainEntry(index: number) {
		chain = chain.filter((_, i) => i !== index);
	}

	function buildPatch(): ConfigUpdate {
		const patch: ConfigUpdate = {};
		const providerConfigs: NonNullable<ConfigUpdate['provider_configs']> = [];
		for (const p of order) {
			const entry: NonNullable<ConfigUpdate['provider_configs']>[number] = { provider: p };
			let touched = false;
			const mode = keyModes[p];
			if (mode === 'clear') {
				entry.api_key = '';
				touched = true;
			} else if (mode === 'set' && (keyInputs[p] ?? '').trim().length > 0) {
				entry.api_key = (keyInputs[p] ?? '').trim();
				touched = true;
			}
			const current = modelLists[p] ?? [];
			const original = originalModels[p] ?? [];
			const added = current.filter((m) => !original.includes(m));
			const removed = original.filter((m) => !current.includes(m));
			if (added.length > 0) {
				entry.add_models = added;
				touched = true;
			}
			if (removed.length > 0) {
				entry.remove_models = removed;
				touched = true;
			}
			if (touched) providerConfigs.push(entry);
		}
		if (providerConfigs.length > 0) patch.provider_configs = providerConfigs;
		if (orderChanged) patch.provider_order = [...order];
		const taskUpdates: NonNullable<ConfigUpdate['task_assignments']> = [];
		for (const role of ROLE_ORDER) {
			const original = originalSelections.get(role) ?? [];
			if (role === 'recipe_ingredients') {
				const same =
					chain.length === original.length &&
					chain.every(
						(e, i) => e.provider === original[i]?.provider && e.model === original[i]?.model
					);
				if (!same) {
					taskUpdates.push({
						role,
						entries: chain.map((e) => ({ provider: e.provider, model_id: e.model }))
					});
				}
				continue;
			}
			const current = selections[role] ?? null;
			const orig = original[0] ?? null;
			const same =
				(current === null && orig === null) ||
				(current !== null &&
					orig !== null &&
					current.provider === orig.provider &&
					current.model === orig.model);
			if (!same) {
				taskUpdates.push({
					role,
					entries:
						current === null ? [] : [{ provider: current.provider, model_id: current.model }]
				});
			}
		}
		if (taskUpdates.length > 0) patch.task_assignments = taskUpdates;
		return patch;
	}

	async function save() {
		if (saveState === 'saving' || !dirty || !onSave) return;
		clearTimeout(timer);
		saveState = 'saving';
		try {
			await onSave(buildPatch());
			saveState = 'saved';
			timer = setTimeout(() => (saveState = 'idle'), 2500);
		} catch {
			saveState = 'error';
			timer = setTimeout(() => (saveState = 'idle'), 4000);
		}
	}

	onDestroy(() => clearTimeout(timer));
</script>

<div
	class="ai-config"
	data-verify-unit="ai-configuration"
	data-verify-state={saveState}
	data-verify-is-admin={String(isAdmin)}
	data-verify-provider-order={providerOrderText}
	data-verify-model-counts={modelCountsText}
	data-verify-task-assignments={assignmentsText}
	data-verify-fallback-order={fallbackOrderText}
	data-verify-dirty={String(dirty)}
	data-verify-setup-state={setupState}
>
	{#if !isAdmin}
		<p class="denied">AI configuration is only available to administrators.</p>
	{:else}
		<section class="ruled" aria-label="Setup status">
			<h2><span class="no">1</span>Setup status</h2>
			{#if readiness === null}
				<p class="status">Checking AI setup…</p>
			{:else}
				<p class="status" class:missing={!readiness.extraction_available}>
					{readiness.extraction_available
						? 'Extraction is ready — at least one provider holds an API key.'
						: 'Extraction needs AI setup — add a provider API key below.'}
				</p>
				<p class="status" class:missing={!readiness.assistant_available}>
					{readiness.assistant_available
						? 'The assistant is ready.'
						: 'The assistant is unavailable until a provider key is added.'}
				</p>
				<p class="status" class:missing={!readiness.ocr_available}>
					{readiness.ocr_available
						? 'PDF text recognition is ready (Gemini).'
						: 'PDF-only books need a Gemini API key for text recognition.'}
				</p>
			{/if}
		</section>

		<section class="ruled" aria-label="Providers">
			<h2><span class="no">2</span>Providers</h2>
			<p class="hint">
				Order sets task fallback priority: an unassigned task uses the first ordered
				provider with a recommendation for it. Keys are write-only and never shown.
			</p>
			{#each order as provider, index (provider)}
				{@const rows = config.providers.find((p) => p.provider === provider)}
				{@const used = referencedModels(provider)}
				<div class="provider" data-provider={provider}>
					<div class="provider-head">
						<span class="provider-name">{provider}</span>
						<span class="provider-position">{index + 1} of {order.length}</span>
						<button
							class="link order-up"
							type="button"
							disabled={index === 0}
							aria-label={`Move ${provider} up`}
							onclick={() => moveProvider(provider, -1)}>Up</button
						>
						<button
							class="link order-down"
							type="button"
							disabled={index === order.length - 1}
							aria-label={`Move ${provider} down`}
							onclick={() => moveProvider(provider, 1)}>Down</button
						>
					</div>
					<div class="control">
						{#if keyModes[provider] === 'keep'}
							<span class="key-status">•••• set</span>
							<button
								class="link key-replace"
								type="button"
								onclick={() => (keyModes = { ...keyModes, [provider]: 'set' })}>Replace</button
							>
							<button
								class="link key-clear"
								type="button"
								onclick={() => (keyModes = { ...keyModes, [provider]: 'clear' })}>Clear</button
							>
						{:else if keyModes[provider] === 'clear'}
							<span class="key-status">Will be cleared on save</span>
							<button
								class="link key-undo"
								type="button"
								onclick={() => (keyModes = { ...keyModes, [provider]: 'keep' })}>Undo</button
							>
						{:else}
							<label class="inline-label" for={`key-${provider}`}>{provider} API key</label>
							<input
								id={`key-${provider}`}
								class="key-input"
								type="password"
								autocomplete="off"
								placeholder="Paste API key"
								value={keyInputs[provider] ?? ''}
								oninput={(e) => (keyInputs = { ...keyInputs, [provider]: e.currentTarget.value })}
							/>
							{#if rows?.api_key_set}
								<button
									class="link key-cancel"
									type="button"
									onclick={() => {
										keyModes = { ...keyModes, [provider]: 'keep' };
										keyInputs = { ...keyInputs, [provider]: '' };
									}}>Cancel</button
								>
							{/if}
						{/if}
					</div>
					<ul class="models" aria-label={`${provider} models`}>
						{#each modelLists[provider] ?? [] as model (model)}
							{@const blocked = used.has(model)}
							<li class="model-row">
								<span class="mono">{model}</span>
								<button
									class="link model-remove"
									type="button"
									data-model={model}
									disabled={blocked}
									title={blocked ? 'Assigned to a task — reassign it first' : `Remove ${model}`}
									aria-label={`Remove ${model} from ${provider}`}
									onclick={() => removeModel(provider, model)}>Remove</button
								>
							</li>
						{/each}
					</ul>
					<div class="control">
						<label class="inline-label" for={`add-model-${provider}`}>Add model</label>
						<input
							id={`add-model-${provider}`}
							class="model-add-input"
							type="text"
							autocomplete="off"
							placeholder="e.g. gemini-3-pro"
							value={newModelInputs[provider] ?? ''}
							oninput={(e) =>
								(newModelInputs = { ...newModelInputs, [provider]: e.currentTarget.value })}
						/>
						<button
							class="link model-add"
							type="button"
							disabled={(newModelInputs[provider] ?? '').trim().length === 0 ||
								(modelLists[provider] ?? []).includes((newModelInputs[provider] ?? '').trim())}
							aria-label={`Add model to ${provider}`}
							onclick={() => addModel(provider)}>Add</button
						>
					</div>
				</div>
			{/each}
		</section>

		<section class="ruled" aria-label="Tasks">
			<h2><span class="no">3</span>Tasks</h2>
			<p class="hint">
				A task without a selection uses the first ordered provider with a recommendation
				for it. Ingredient parsing tries its list in order, primary first.
			</p>
			{#each GROUPS as group (group.title)}
				<h3>{group.title}</h3>
				{#each group.roles as role (role)}
					{#if role === 'recipe_ingredients'}
						<div class="task" data-role={role}>
							<span class="task-label" id="label-recipe-ingredients">Ingredient parsing</span>
							{#if chain.length === 0}
								<p class="hint">Unassigned — resolves to the ordered provider default.</p>
							{/if}
							<ol class="chain">
								{#each chain as entry, i (i)}
									<li class="chain-row">
										<span class="mono">{i + 1}. {entry.provider} · {entry.model}</span>
										<button
											class="link chain-up"
											type="button"
											disabled={i === 0}
											aria-label={`Move fallback ${i + 1} up`}
											onclick={() => moveChainEntry(i, -1)}>Up</button
										>
										<button
											class="link chain-down"
											type="button"
											disabled={i === chain.length - 1}
											aria-label={`Move fallback ${i + 1} down`}
											onclick={() => moveChainEntry(i, 1)}>Down</button
										>
										<button
											class="link chain-remove"
											type="button"
											data-position={i}
											aria-label={`Remove fallback ${i + 1}`}
											onclick={() => removeChainEntry(i)}>Remove</button
										>
									</li>
								{/each}
							</ol>
							<div class="control">
								<label class="inline-label" for="chain-provider">Fallback provider</label>
								<select
									id="chain-provider"
									class="chain-provider"
									value={chainProvider}
									onchange={(e) => {
										const next = (e.currentTarget as HTMLSelectElement).value as AiProvider | '';
										chainProvider = next;
										chainModel = '';
									}}
								>
									<option value="">— Select —</option>
									{#each order as p (p)}
										<option value={p}>{p}</option>
									{/each}
								</select>
								<label class="inline-label" for="chain-model">Fallback model</label>
								<select
									id="chain-model"
									class="chain-model"
									value={chainModel}
									disabled={chainProvider === ''}
									onchange={(e) => (chainModel = (e.currentTarget as HTMLSelectElement).value)}
								>
									<option value="">— Select —</option>
									{#each chainModels() as m (m)}
										<option value={m}>{m}</option>
									{/each}
								</select>
								<button
									class="link chain-add"
									type="button"
									disabled={chainProvider === '' || chainModel === ''}
									onclick={addChainEntry}>Add fallback</button
								>
							</div>
							<p class="recommendation">
								Recommended: {recommendation('recipe_ingredients', order[0] ?? 'GEMINI') !== null
									? `${order[0]} · ${recommendation('recipe_ingredients', order[0] ?? 'GEMINI')}`
									: 'the ordered provider default'}
							</p>
						</div>
					{:else}
						{@const sel = selections[role] ?? null}
						<div class="task" data-role={role}>
							<label class="task-label" for={`task-provider-${role}`}>{ROLE_LABELS[role]}</label>
							<div class="control">
								<select
									id={`task-provider-${role}`}
									class="task-provider"
									data-role={role}
									value={sel?.provider ?? ''}
									onchange={(e) =>
										selectTaskProvider(role, (e.currentTarget as HTMLSelectElement).value as AiProvider | '')}
								>
									<option value="">— Default —</option>
									{#each order as p (p)}
										<option value={p}>{p}</option>
									{/each}
								</select>
								<label class="inline-label" for={`task-model-${role}`}>Model</label>
								<select
									id={`task-model-${role}`}
									class="task-model"
									data-role={role}
									value={sel?.model ?? ''}
									disabled={sel === null}
									onchange={(e) => selectTaskModel(role, (e.currentTarget as HTMLSelectElement).value)}
								>
									<option value="">— Select —</option>
									{#each sel !== null ? (modelLists[sel.provider] ?? []) : [] as m (m)}
										<option value={m}>{m}</option>
									{/each}
								</select>
							</div>
							<p class="recommendation">
								{#if sel !== null}
									{@const rec = recommendation(role, sel.provider)}
									Recommended: {rec !== null ? `${sel.provider} · ${rec}` : 'none for this provider'}
								{:else}
									{@const first = order
										.map((p) => ({ p, rec: recommendation(role, p) }))
										.find((x) => x.rec !== null)}
									Recommended: {first ? `${first.p} · ${first.rec}` : 'none configured'}
								{/if}
								{#if role === 'ocr'} (Gemini is the only OCR-capable provider){/if}
							</p>
						</div>
					{/if}
				{/each}
			{/each}
		</section>

		<div class="actions">
			<button
				class="save ai-save"
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
	{/if}
</div>

<style>
	.ai-config {
		display: flex;
		flex-direction: column;
	}
	.denied {
		font-family: var(--f-serif);
		font-size: 1.1rem;
		color: var(--muted);
	}
	.ruled {
		padding: 0.4rem 0 1.6rem;
		border-bottom: var(--border);
	}
	.ruled h2 {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.8rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 1.6rem 0 0.4rem;
	}
	.ruled h2 .no {
		font-family: var(--f-mono);
		color: var(--clay-deep);
		margin-right: 0.6rem;
	}
	.ruled h3 {
		font-family: var(--f-serif);
		font-weight: 400;
		font-size: 1.25rem;
		margin: 1.4rem 0 0.2rem;
	}
	.hint {
		margin: 0.4rem 0;
		font-family: var(--f-serif);
		color: var(--muted);
	}
	.status {
		margin: 0.4rem 0;
		font-family: var(--f-serif);
	}
	.status.missing {
		color: var(--clay-deep);
	}
	.provider {
		padding: 1rem 0;
		border-bottom: var(--border);
	}
	.provider-head {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 0.9rem;
	}
	.provider-name {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 1rem;
	}
	.provider-position {
		font-family: var(--f-mono);
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		color: var(--muted);
	}
	.control {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.6rem 0.9rem;
		margin-top: 0.6rem;
	}
	.inline-label {
		font-family: var(--f-grotesk);
		font-size: 0.8rem;
		color: var(--muted);
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
	select:focus,
	input:focus {
		border-color: var(--clay-deep);
		outline: none;
	}
	select {
		min-width: 12rem;
	}
	input[type='password'],
	input[type='text'] {
		min-width: 14rem;
	}
	.key-status {
		font-family: var(--f-mono);
		font-size: 0.8rem;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	.models {
		list-style: none;
		margin: 0.6rem 0 0;
		padding: 0;
	}
	.model-row {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		padding: 0.35rem 0;
	}
	.mono {
		font-family: var(--f-mono);
		font-size: 0.85rem;
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
	.link:hover:not(:disabled) {
		color: var(--ink);
	}
	.link:disabled {
		color: var(--muted);
		text-decoration: none;
		cursor: default;
	}
	.task {
		padding: 0.9rem 0;
		border-bottom: var(--border);
	}
	.task-label {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		display: block;
		margin-bottom: 0.2rem;
	}
	.recommendation {
		margin: 0.4rem 0 0;
		font-family: var(--f-mono);
		font-size: 0.75rem;
		letter-spacing: 0.03em;
		color: var(--muted);
	}
	.chain {
		list-style: none;
		margin: 0.4rem 0 0;
		padding: 0;
	}
	.chain-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.9rem;
		padding: 0.35rem 0;
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
</style>
