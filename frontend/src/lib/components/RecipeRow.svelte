<script module lang="ts">
	export type RecipeRowData = {
		id: string;
		name: string;
		bookId: string;
		bookTitle: string;
		bookAuthor: string;
		keywords: string[];
		/** Whether the reader has opened this one — marks the row as already read. */
		isSeen?: boolean;
	};
</script>

<script lang="ts">
	import { cleanTitle } from '$lib/title';
	import { keywordHref } from '$lib/api/recipes';

	// `contextQuery` carries the originating search (criteria + ordering) into the
	// recipe link, so the detail page's prev/next follow the search order.
	// `onKeyword`, when set, intercepts a plain click on a keyword chip to filter
	// in place (the search page); without it the chip just navigates to its href.
	let {
		id,
		name,
		bookId,
		bookTitle,
		bookAuthor,
		keywords,
		isSeen = false,
		contextQuery = '',
		onRemove,
		onKeyword
	}: RecipeRowData & {
		contextQuery?: string;
		onRemove?: () => void;
		onKeyword?: (name: string) => void;
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

<li class="row" data-verify-seen={isSeen ? 'true' : 'false'}>
	<div class="line">
		<a class="name" class:read={isSeen} href={`/recipes/${id}${contextQuery ? `?${contextQuery}` : ''}`}
			>{name}</a
		>
		{#if isSeen}<span class="read-flag">Read</span>{/if}
		<a class="source" href={`/books/${bookId}`}>
			{displayTitle}<span class="sep" aria-hidden="true">·</span><span class="author">{bookAuthor}</span>
		</a>
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

	.line {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.3rem 1.25rem;
	}

	.name {
		font-family: var(--f-serif);
		font-size: 1.2rem;
		line-height: 1.3;
		color: var(--ink);
		text-decoration: none;
		transition: color 0.18s var(--ease-out);
	}

	.name:hover {
		color: var(--clay-deep);
	}
	/* A row already read steps back rather than disappearing — the list still reads
	   as one list, with what's behind you quieter. */
	.name.read {
		color: var(--muted);
	}

	.read-flag {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--clay-deep);
		white-space: nowrap;
	}

	.source {
		margin-left: auto;
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
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
		color: var(--clay-deep);
		border-bottom-color: var(--clay);
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
		font-size: 0.66rem;
		letter-spacing: 0.03em;
		padding: 0.15rem 0.5rem;
		border-radius: 3px;
		text-decoration: none;
	}

	.chip:hover,
	.chip:focus-visible {
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.chip:focus-visible {
		outline: 2px solid var(--clay);
		outline-offset: 1px;
	}

	.chip-clay {
		background: var(--chip-clay);
		color: var(--chip-clay-c);
	}
	.chip-blue {
		background: var(--chip-blue);
		color: var(--chip-blue-c);
	}
	.chip-green {
		background: var(--chip-green);
		color: var(--chip-green-c);
	}

	@media (max-width: 560px) {
		.source {
			margin-left: 0;
			white-space: normal;
		}
	}
</style>
