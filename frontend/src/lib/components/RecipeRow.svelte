<script module lang="ts">
	import type { ListPanelApi } from '$lib/api/lists';

	/** Switches on the per-row add-to-list picker; passed through by every surface. */
	export type RowPickerHook = {
		api?: ListPanelApi;
		/** Fired after a successful membership toggle, with the row's recipe id. */
		onMembershipChange?: (recipeId: string, listId: string, contains: boolean) => void;
	};

	export type RecipeRowData = {
		id: string;
		name: string;
		bookId: string;
		bookTitle: string;
		bookAuthor: string;
		keywords: string[];
		/** Whether the reader has opened this one — marks the row as already read. */
	};
</script>

<script lang="ts">
	import { cleanTitle } from '$lib/title';
	import { keywordHref } from '$lib/api/recipes';
	import RowListPicker from './RowListPicker.svelte';

	// `contextQuery` carries the originating search (criteria + ordering) into the
	// recipe link, so the detail page's prev/next follow the search order.
	// `onKeyword`, when set, intercepts a plain click on a keyword chip to filter
	// in place (the search page); without it the chip just navigates to its href.
	// `listPicker` switches on the per-row add-to-list control (self-fetching).
	// `selectable` puts the row in selection mode: a leading checkbox, reported
	// through `onSelect` — a deliberate, mode-scoped exception to DESIGN §5's
	// "no leading number" (the resting row is unchanged).
	let {
		id,
		name,
		bookId,
		bookTitle,
		bookAuthor,
		keywords,
		contextQuery = '',
		onRemove,
		onKeyword,
		listPicker,
		selectable = false,
		selected = false,
		onSelect
	}: RecipeRowData & {
		contextQuery?: string;
		onRemove?: () => void;
		onKeyword?: (name: string) => void;
		listPicker?: RowPickerHook;
		selectable?: boolean;
		selected?: boolean;
		onSelect?: (selected: boolean) => void;
	} = $props();

	// Calibre titles carry a subtitle after a colon; show the clean pre-colon title.
	let displayTitle = $derived(cleanTitle(bookTitle));

	// Rotating chip tints (DESIGN §3.1).
	const tints = ['clay', 'blue', 'green'] as const;

	// A plain left-click filters the current view in place; modifier/middle clicks
	// fall through to the href so the keyword opens in a new tab.
	function onChipClick(e: MouseEvent, kw: string): void {
		if (!onKeyword || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
		e.preventDefault();
		onKeyword(kw);
	}
</script>

<li class="row" class:selected>
	<div class="line">
		{#if selectable}
			<input
				class="select"
				type="checkbox"
				checked={selected}
				aria-label={`Select ${name}`}
				onchange={(e) => onSelect?.(e.currentTarget.checked)}
			/>
		{/if}
		<a class="name" href={`/recipes/${id}${contextQuery ? `?${contextQuery}` : ''}`}>{name}</a>
		<a class="source" href={`/books/${bookId}`}>
			{displayTitle}<span class="sep" aria-hidden="true">·</span><span class="author">{bookAuthor}</span>
		</a>
		{#if listPicker}
			<RowListPicker
				recipeId={id}
				recipeName={name}
				api={listPicker.api}
				onMembershipChange={(listId, contains) =>
					listPicker?.onMembershipChange?.(id, listId, contains)}
			/>
		{/if}
		{#if onRemove}
			<button
				class="remove"
				type="button"
				aria-label={`Remove ${name} from this list`}
				onclick={() => onRemove?.()}
			>
				Remove
			</button>
		{/if}
	</div>
	{#if keywords.length}
		<ul class="chips">
			{#each keywords as kw, i (kw)}
				<li>
					<a
						class={`chip chip-${tints[i % tints.length]}`}
						href={keywordHref(kw)}
						onclick={(e) => onChipClick(e, kw)}>{kw}</a
					>
				</li>
			{/each}
		</ul>
	{/if}
</li>

<style>
	.row {
		padding: 1rem 0;
		border-bottom: var(--border);
	}
	.row.selected {
		background: var(--bg-warm);
	}

	.select {
		align-self: center;
		width: 1rem;
		height: 1rem;
		margin: 0;
		accent-color: var(--accent);
		cursor: pointer;
	}

	.line {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.3rem 1.25rem;
	}

	.name {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 1.05rem;
		line-height: 1.3;
		color: var(--ink);
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}

	.name:hover {
		color: var(--accent-deep);
	}
	.source {
		margin-left: auto;
		font-family: var(--f-mono);
		font-size: 0.68rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
		text-decoration: none;
		white-space: nowrap;
		transition: color 0.18s var(--ease-out);
	}

	.source:hover {
		color: var(--ink);
	}

	.sep {
		margin: 0 0.4rem;
		color: var(--faint);
	}

	.remove {
		font-family: var(--f-grotesk);
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--muted);
		background: none;
		border: none;
		border-bottom: 1px solid transparent;
		padding: 0;
		cursor: pointer;
		white-space: nowrap;
		transition: color 0.18s var(--ease-out);
	}
	.remove:hover {
		color: var(--accent-deep);
		border-bottom-color: var(--accent);
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		list-style: none;
		margin: 0.55rem 0 0;
		padding: 0;
	}

	.chip {
		display: inline-block;
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		text-decoration: none;
	}

	.chip:hover,
	.chip:focus-visible {
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.chip:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	.chip-clay,
	.chip-blue,
	.chip-green {
		color: var(--chip-accent-c);
	}
	.chips li + li::before {
		content: '·';
		color: var(--faint);
		margin-right: 0.15rem;
	}

	@media (max-width: 560px) {
		.source {
			margin-left: 0;
			white-space: normal;
		}
	}
</style>
