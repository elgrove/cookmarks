<script module lang="ts">
	import type { RecipeFilters } from '$lib/api/recipe-filters';
	export type AdvancedRecipeSearchProps = {
		open?: boolean;
		filters?: RecipeFilters;
		books?: { id: string; title: string }[];
		lists?: { id: string; name: string }[];
		lookupLoading?: boolean;
		lookupError?: string;
		onApply?: (filters: RecipeFilters) => void;
		onClose?: () => void;
	};
</script>

<script lang="ts">
	import { untrack } from 'svelte';
	import {
		emptyFilters,
		fieldLabels,
		filterFields,
		operatorLabels,
		operatorsFor,
		recipeFiltersSchema,
		normaliseFilters,
		type FilterField,
		type FilterRule
	} from '$lib/api/recipe-filters';
	let {
		open = false,
		filters = emptyFilters(),
		books = [],
		lists = [],
		lookupError = '',
		lookupLoading = false,
		onApply,
		onClose
	}: AdvancedRecipeSearchProps = $props();
	let draft = $state<RecipeFilters>(emptyFilters());
	let dialog = $state<HTMLDialogElement>();
	let validation = $derived(recipeFiltersSchema.safeParse(draft));
	let invalid = $derived(
		validation.success ? '' : (validation.error.issues[0]?.message ?? 'Check the rules.')
	);
	$effect(() => {
		if (open)
			untrack(() => {
				draft = JSON.parse(JSON.stringify(filters));
			});
	});
	$effect(() => {
		if (!open || !dialog) return;
		if (typeof dialog.showModal === 'function') dialog.showModal();
		else dialog.setAttribute('open', '');
	});
	function addRule() {
		if (draft.rules.length < 20)
			draft.rules = [...draft.rules, { field: 'name', operator: 'contains', value: '' }];
	}
	function changeField(index: number, field: FilterField) {
		draft.rules[index] = {
			field,
			operator: operatorsFor(field)[0],
			value: ['favourite', 'has_image'].includes(field) ? true : ''
		};
	}
	function changeOperator(index: number, operator: FilterRule['operator']) {
		draft.rules[index] = {
			...draft.rules[index],
			operator,
			value: operator.startsWith('is_') ? null : ''
		};
	}
	function pickerOptions(rule: FilterRule) {
		const options =
			rule.field === 'list'
				? lists.map((list) => ({ id: list.id, label: list.name }))
				: books.map((book) => ({ id: book.id, label: book.title }));
		return options.map((option, index) => ({
			...option,
			label:
				options.filter((other) => other.label === option.label).length > 1
					? `${option.label} (${options.slice(0, index + 1).filter((other) => other.label === option.label).length})`
					: option.label
		}));
	}
	function needsPicker(rule: FilterRule) {
		return (
			rule.field === 'list' || (rule.field === 'book' && ['eq', 'neq'].includes(rule.operator))
		);
	}
	function pickerValue(rule: FilterRule) {
		return (
			pickerOptions(rule).find((o) => o.id === rule.value)?.label ??
			(/^[0-9a-f-]{36}$/i.test(String(rule.value))
				? `Unavailable ${rule.field}`
				: String(rule.value ?? ''))
		);
	}
	function setPicker(index: number, value: string) {
		draft.rules[index].value =
			pickerOptions(draft.rules[index]).find((o) => o.label === value)?.id ?? value;
	}
	function apply() {
		const parsed = recipeFiltersSchema.safeParse(draft);
		if (parsed.success) onApply?.(normaliseFilters(parsed.data));
	}
</script>

<div
	data-verify-unit="advanced-recipe-search"
	data-verify-open={String(open)}
	data-verify-rules={JSON.stringify(draft.rules)}
	data-verify-match={draft.match}
	data-verify-valid={String(validation.success)}
>
	{#if open}
		<dialog
			bind:this={dialog}
			aria-labelledby="advanced-search-title"
			oncancel={(e) => {
				e.preventDefault();
				onClose?.();
			}}
			onclick={(e) => {
				if (e.target === dialog) onClose?.();
			}}
			onkeydown={(e) => {
				if (e.key === 'Escape') {
					e.preventDefault();
					onClose?.();
				}
			}}
		>
			<div class="panel">
				<header>
					<div>
						<p class="label">Refine the library</p>
						<h2 id="advanced-search-title">Advanced search</h2>
					</div>
					<button
						class="close"
						type="button"
						aria-label="Close advanced search"
						onclick={() => onClose?.()}>×</button
					>
				</header>
				<form
					onsubmit={(e) => {
						e.preventDefault();
						apply();
					}}
				>
					<div class="body">
						<label class="match"
							>Match
							<select aria-label="Combine rules" bind:value={draft.match}
								><option value="all">all rules</option><option value="any">any rule</option></select
							>
						</label>
						<p class="hint">
							These rules also apply with your search text and selected keyword chips. Cuisine
							matches flat keywords.
						</p>
						{#if lookupLoading}<p class="lookup-error" role="status">
								Loading books and lists…
							</p>{/if}
						{#if lookupError}<p class="lookup-error" role="status">
								{lookupError} You can still use text rules.
							</p>{/if}
						{#if !draft.rules.length}<p class="empty">
								Add a rule to filter a recipe field, keyword category, book, or collection.
							</p>{/if}
						<ol class="rules">
							{#each draft.rules as rule, index}
								<li class="rule" data-rule-field={rule.field}>
									<span class="index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
									<label
										><span class="label">Field</span><select
											aria-label={`Field for rule ${index + 1}`}
											value={rule.field}
											onchange={(e) => changeField(index, e.currentTarget.value as FilterField)}
										>
											{#each filterFields as field}<option value={field}
													>{fieldLabels[field]}</option
												>{/each}
										</select></label
									>
									<label
										><span class="label">Operator</span><select
											aria-label={`Operator for rule ${index + 1}`}
											value={rule.operator}
											onchange={(e) =>
												changeOperator(index, e.currentTarget.value as FilterRule['operator'])}
										>
											{#each operatorsFor(rule.field) as operator}<option value={operator}
													>{operatorLabels[operator]}</option
												>{/each}
										</select></label
									>
									{#if rule.field === 'favourite' || rule.field === 'has_image'}
										<label
											><span class="label">Value</span><select
												aria-label={`Value for rule ${index + 1}`}
												value={String(rule.value)}
												onchange={(e) => {
													rule.value = e.currentTarget.value === 'true';
												}}
												><option value="true">Yes</option><option value="false">No</option></select
											></label
										>
									{:else if !rule.operator.startsWith('is_')}
										<label class="value"
											><span class="label">Value</span>
											{#if needsPicker(rule)}
												<input
													type="text"
													autocomplete="off"
													aria-label={`Value for rule ${index + 1}`}
													list={`advanced-picker-${index}`}
													value={pickerValue(rule)}
													placeholder={rule.field === 'book' ? 'Find a book…' : 'Find a list…'}
													oninput={(e) => setPicker(index, e.currentTarget.value)}
												/>
												<datalist id={`advanced-picker-${index}`}
													>{#each pickerOptions(rule) as option}<option value={option.label}
														></option>{/each}</datalist
												>
											{:else}
												<input
													type="text"
													autocomplete="off"
													aria-label={`Value for rule ${index + 1}`}
													maxlength="500"
													value={String(rule.value ?? '')}
													placeholder="Enter text…"
													oninput={(e) => {
														rule.value = e.currentTarget.value;
													}}
												/>
											{/if}
										</label>
									{/if}
									<button
										class="remove"
										type="button"
										aria-label={`Remove rule ${index + 1}`}
										onclick={() => {
											draft.rules = draft.rules.filter((_, i) => i !== index);
										}}>×</button
									>
								</li>
							{/each}
						</ol>
						<button class="add" type="button" disabled={draft.rules.length >= 20} onclick={addRule}
							>+ Add rule</button
						>
						{#if invalid}<p class="invalid" role="alert">{invalid}</p>{/if}
					</div>
					<footer>
						<button
							class="clear-rules"
							type="button"
							onclick={() => {
								draft = emptyFilters();
							}}>Clear</button
						>
						<button class="cancel" type="button" onclick={() => onClose?.()}>Cancel</button>
						<button class="apply" type="submit" disabled={!validation.success}>Apply filters</button
						>
					</footer>
				</form>
			</div>
		</dialog>
	{/if}
</div>

<style>
	dialog {
		width: min(64rem, calc(100vw - 2rem));
		max-height: calc(100dvh - 2rem);
		padding: 0;
		border: 2px solid var(--ink);
		color: var(--ink);
		background: var(--bg);
		overflow: auto;
		overscroll-behavior: contain;
	}
	dialog::backdrop {
		background: rgb(15 20 18 / 55%);
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: start;
		padding: 1.5rem 1.75rem;
		border-bottom: var(--rule);
	}
	header .label {
		margin: 0 0 0.5rem;
	}
	h2 {
		font-family: var(--f-grotesk);
		font-size: 1.7rem;
		letter-spacing: -0.02em;
		margin: 0;
	}
	.body {
		padding: 1.5rem 1.75rem;
	}
	.match {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-family: var(--f-mono);
		font-size: 0.8rem;
		text-transform: uppercase;
	}
	.hint,
	.empty,
	.lookup-error {
		font-size: 0.85rem;
		color: var(--muted);
		line-height: 1.5;
	}
	.rules {
		list-style: none;
		margin: 1.5rem 0 1rem;
		padding: 0;
	}
	.rule {
		display: grid;
		grid-template-columns: 1.5rem minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.35fr) 2rem;
		gap: 0.65rem;
		align-items: end;
		padding: 1rem 0;
		border-top: var(--border);
	}
	.index {
		align-self: center;
		font-family: var(--f-mono);
		font-size: 0.7rem;
		color: var(--accent);
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		min-width: 0;
	}
	.match {
		flex-direction: row;
	}
	select,
	input {
		box-sizing: border-box;
		width: 100%;
		min-width: 0;
		border: 1px solid var(--ink);
		border-radius: 0;
		background: var(--card);
		color: var(--ink);
		font-family: var(--f-mono);
		font-size: 0.75rem;
		padding: 0.65rem 0.5rem;
	}
	.match select {
		width: auto;
	}
	button {
		font-family: var(--f-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
		padding: 0.65rem 0.85rem;
		color: var(--ink);
		border: 1px solid var(--ink);
		border-radius: 0;
		background: var(--card);
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.close,
	.remove {
		border: 0;
		font-size: 1.25rem;
		padding: 0.3rem;
		background: transparent;
	}
	.remove {
		grid-column: 5;
	}
	.invalid {
		font-size: 0.85rem;
		color: var(--ink);
		border-left: 2px solid var(--accent);
		padding-left: 0.75rem;
	}
	footer {
		position: sticky;
		bottom: 0;
		display: flex;
		gap: 0.65rem;
		justify-content: end;
		padding: 1rem 1.75rem;
		border-top: var(--rule);
		background: var(--bg);
	}
	.clear-rules {
		margin-right: auto;
	}
	.apply {
		background: var(--accent);
		color: white;
		border-color: var(--accent);
	}
	:is(button, input, select):focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}
	@media (max-width: 600px) {
		header,
		.body {
			padding: 1.1rem;
		}
		.rule {
			grid-template-columns: 1.25rem minmax(0, 1fr) 2rem;
			align-items: start;
		}
		.rule label {
			grid-column: 2;
		}
		.index {
			grid-column: 1;
			grid-row: 1;
		}
		.remove {
			grid-column: 3;
			grid-row: 1;
		}
		footer {
			padding: 0.85rem;
			gap: 0.4rem;
		}
		footer button {
			padding: 0.65rem 0.55rem;
		}
	}
</style>
