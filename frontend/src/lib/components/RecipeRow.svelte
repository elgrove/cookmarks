<script module lang="ts">
	export type RecipeRowData = {
		id: string;
		name: string;
		bookId: string;
		bookTitle: string;
		bookAuthor: string;
		keywords: string[];
	};
</script>

<script lang="ts">
	// `contextQuery` carries the originating search (criteria + ordering) into the
	// recipe link, so the detail page's prev/next follow the search order.
	let {
		id,
		name,
		bookId,
		bookTitle,
		bookAuthor,
		keywords,
		contextQuery = '',
		onRemove
	}: RecipeRowData & { contextQuery?: string; onRemove?: () => void } = $props();

	// Rotating chip tints (DESIGN §3.1).
	const tints = ['clay', 'blue', 'green'] as const;
</script>

<li class="row">
	<div class="line">
		<a class="name" href={`/recipes/${id}${contextQuery ? `?${contextQuery}` : ''}`}>{name}</a>
		<a class="source" href={`/books/${bookId}`}>
			{bookTitle}<span class="sep" aria-hidden="true">·</span><span class="author">{bookAuthor}</span>
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
				<li class={`chip chip-${tints[i % tints.length]}`}>{kw}</li>
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
		font-family: var(--f-mono);
		font-size: 0.66rem;
		letter-spacing: 0.03em;
		padding: 0.15rem 0.5rem;
		border-radius: 3px;
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
