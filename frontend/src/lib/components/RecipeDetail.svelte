<script module lang="ts">
	export type RecipeDetailData = {
		id: string;
		bookId: string;
		bookTitle: string;
		bookAuthor: string;
		bookHasCover: boolean;
		name: string;
		description: string | null;
		ingredients: string[];
		instructions: string[];
		yields: string | null;
		keywords: string[];
		hasImage: boolean;
		isFavourite: boolean;
		/** The navigation ordering this page was reached through ('book' | 'search'). */
		context: string;
		/** The query string carried into prev/next links so they keep this ordering. */
		contextQuery: string;
		/** For a search context, the URL back to the originating search (else null). */
		searchHref: string | null;
		/** Adjacent recipes in `context` order, for the prev/next pager (null at the ends). */
		previous: { id: string; name: string } | null;
		next: { id: string; name: string } | null;
	};

	// Rotating chip tints (DESIGN §3.1), assigned deterministically per keyword.
	const CHIP_TINTS = ['', 'b', 'g'] as const;
	function chipClass(keyword: string): string {
		let h = 0;
		for (let i = 0; i < keyword.length; i++) h = (h + keyword.charCodeAt(i)) % CHIP_TINTS.length;
		return CHIP_TINTS[h];
	}
</script>

<script lang="ts">
	import { plainText } from '$lib/html';
	import { cleanTitle } from '$lib/title';
	import type { ListMembership } from '$lib/api/lists';
	import FavouriteToggle from './FavouriteToggle.svelte';
	import ListPicker from './ListPicker.svelte';

	let {
		recipe,
		lists,
		onToggleFavourite,
		onToggleList,
		onCreateList
	}: {
		recipe: RecipeDetailData;
		/** List memberships for the add-to-list control; the picker is shown once loaded. */
		lists?: ListMembership[];
		onToggleFavourite?: () => void;
		onToggleList?: (listId: string, contains: boolean) => void;
		onCreateList?: (name: string) => void;
	} = $props();

	let coverFailed = $state(false);
	let imageFailed = $state(false);
	let expanded = $state(false);
	let showCover = $derived(recipe.bookHasCover && !coverFailed);
	// Most recipes carry no image (DESIGN §7); show the figure only when the source
	// had one, and fall back to the text-first default if the stream fails to load.
	let showImage = $derived(recipe.hasImage && !imageFailed);

	// The book's display title (pre-colon) for the breadcrumb and provenance.
	let bookTitle = $derived(cleanTitle(recipe.bookTitle));
	// Calibre descriptions carry HTML; render the intro as plain serif text.
	let lede = $derived(plainText(recipe.description ?? ''));
</script>

{#snippet actionButtons()}
	<FavouriteToggle
		isFavourite={recipe.isFavourite}
		recipeName={recipe.name}
		onToggle={onToggleFavourite}
	/>
	{#if lists}
		<ListPicker {lists} onToggle={onToggleList} onCreate={onCreateList} />
	{/if}
{/snippet}

<article
	class="recipe"
	data-verify-unit="recipe-detail"
	data-verify-id={recipe.id}
	data-verify-ingredients={recipe.ingredients.length}
	data-verify-steps={recipe.instructions.length}
	data-verify-keywords={recipe.keywords.length}
	data-verify-has-image={recipe.hasImage ? 'true' : 'false'}
	data-verify-favourite={recipe.isFavourite ? 'true' : 'false'}
	data-verify-context={recipe.context}
	data-verify-prev={recipe.previous?.id ?? ''}
	data-verify-next={recipe.next?.id ?? ''}
>
	<div class="topbar">
		<nav class="crumb" aria-label="Breadcrumb">
			{#if recipe.context === 'search' && recipe.searchHref}
				<a href="/recipes">Recipes</a><span class="sep">›</span><a href={recipe.searchHref}
					>Search results</a
				><span class="sep">›</span><span class="here">{recipe.name}</span>
			{:else}
				<a href="/books">Books</a><span class="sep">›</span><a
					href={`/books?author=${encodeURIComponent(recipe.bookAuthor)}`}>{recipe.bookAuthor}</a
				><span class="sep">›</span><a href={`/books/${recipe.bookId}`}>{bookTitle}</a><span
					class="sep">›</span
				><span class="here">{recipe.name}</span>
			{/if}
		</nav>

		{#if recipe.previous || recipe.next}
			<div class="pager">
				{#if recipe.previous}
					<a
						class="pg prev"
						href={`/recipes/${recipe.previous.id}?${recipe.contextQuery}`}
						title={recipe.previous.name}
						aria-label={`Previous recipe: ${recipe.previous.name}`}
					>
						<span class="ar" aria-hidden="true">‹</span> Prev
					</a>
				{/if}
				{#if recipe.next}
					<a
						class="pg next"
						href={`/recipes/${recipe.next.id}?${recipe.contextQuery}`}
						title={recipe.next.name}
						aria-label={`Next recipe: ${recipe.next.name}`}
					>
						Next <span class="ar" aria-hidden="true">›</span>
					</a>
				{/if}
			</div>
		{/if}
	</div>

	<header class="masthead" class:has-image={showImage}>
		<div class="head">
			<div class="head-main">
				<h1 class="display">{recipe.name}</h1>
				{#if recipe.keywords.length}
					<div class="chips">
						{#each recipe.keywords as kw (kw)}
							<span class="chip {chipClass(kw)}">{kw}</span>
						{/each}
					</div>
				{/if}
				{#if showImage}
					<!-- The image takes the rail; the actions sit left under the chips and
					     the yield drops down to head the ingredients (see the body). -->
					<div class="actions inline">{@render actionButtons()}</div>
				{:else if recipe.yields}
					<p class="yields">{recipe.yields}</p>
				{/if}
				{#if lede}
					<div class="lede" class:clamped={!expanded && lede.length > 360}>
						<p>{lede}</p>
					</div>
					{#if lede.length > 360}
						<button class="readmore" type="button" onclick={() => (expanded = !expanded)}>
							{expanded ? 'Read less' : 'Read more'}
						</button>
					{/if}
				{/if}
			</div>
			{#if showImage}
				<figure class="recipe-figure">
					<img
						class="recipe-image"
						src={`/api/recipes/${recipe.id}/image`}
						alt={`Image accompanying ${recipe.name}`}
						onerror={() => (imageFailed = true)}
					/>
				</figure>
			{:else}
				<div class="actions">{@render actionButtons()}</div>
			{/if}
		</div>
	</header>

	<div class="body">
		<section class="block">
			{#if showImage && recipe.yields}<p class="yields yield-lead">{recipe.yields}</p>{/if}
			<p class="label">Ingredients</p>
			{#if recipe.ingredients.length}
				<ul class="ingredients">
					{#each recipe.ingredients as ing, i (i)}
						<li>{ing}</li>
					{/each}
				</ul>
			{:else}
				<p class="empty">No ingredients listed.</p>
			{/if}
		</section>

		<section class="block method-col">
			<p class="label">Method</p>
			{#if recipe.instructions.length}
				<ol class="method">
					{#each recipe.instructions as step, i (i)}
						<li>
							<span class="stepno" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
							<span class="steptext">{step}</span>
						</li>
					{/each}
				</ol>
			{:else}
				<p class="empty">No method recorded.</p>
			{/if}
		</section>
	</div>

	<section class="prov">
		<p class="label">From the book</p>
		<a class="provlink" href={`/books/${recipe.bookId}`}>
			<span class="provplate">
				{#if showCover}
					<img
						class="provcover"
						src={`/api/books/${recipe.bookId}/cover`}
						alt={`Cover of ${bookTitle}`}
						onerror={() => (coverFailed = true)}
					/>
				{:else}
					<span class="provplate-title" aria-hidden="true">{bookTitle}</span>
				{/if}
			</span>
			<span class="provmeta">
				<span class="provtitle">{bookTitle}</span>
				<span class="provauthor">{recipe.bookAuthor}</span>
			</span>
		</a>
	</section>
</article>

<style>
	.recipe {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 1.35rem var(--page-h) 4rem;
		animation: fadeUp 0.6s var(--ease-out) both;
	}

	/* Breadcrumb on the left, the prev/next pager on the right (desktop). */
	.topbar {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1.25rem 1.75rem;
		flex-wrap: wrap;
		padding-bottom: 1.15rem;
		border-bottom: var(--border);
		margin-bottom: 1.05rem;
	}
	.crumb {
		font-family: var(--f-mono);
		font-size: 0.7rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		min-width: 0;
		flex: 1 1 auto;
	}
	.crumb a {
		text-decoration: none;
		color: var(--muted);
	}
	.crumb a:hover {
		color: var(--clay-deep);
	}
	.crumb .sep {
		color: var(--faint);
		margin: 0 0.55rem;
	}
	.crumb .here {
		color: var(--ink);
	}

	.pager {
		display: flex;
		gap: 1.25rem;
		flex: none;
	}
	.pg {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-family: var(--f-grotesk);
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--muted);
		text-decoration: none;
		white-space: nowrap;
		transition: color 0.18s var(--ease-out);
	}
	.pg:hover {
		color: var(--ink);
	}
	.pg .ar {
		color: var(--clay);
		font-size: 0.95rem;
		line-height: 1;
	}

	/* Masthead — full width. No image: actions sit in the right rail (top-right).
	   With an image: the rail becomes the photo and the actions ride the yield line. */
	.masthead {
		margin-bottom: 2.75rem;
		padding-bottom: 2.25rem;
		border-bottom: var(--border-strong);
	}
	.head {
		display: grid;
		grid-template-columns: 1fr minmax(190px, 230px);
		column-gap: 3.5rem;
		align-items: start;
	}
	.masthead.has-image .head {
		grid-template-columns: 1fr minmax(260px, 330px);
	}
	.head-main {
		min-width: 0;
	}
	.display {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.5rem, 5.2vw, 4.1rem);
		line-height: 1.02;
		letter-spacing: -0.015em;
		margin: 0;
		overflow-wrap: break-word;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 1.2rem;
	}
	.chip {
		font-family: var(--f-grotesk);
		font-size: 0.68rem;
		font-weight: 500;
		line-height: 1.2;
		letter-spacing: 0.01em;
		padding: 0.2rem 0.55rem;
		border-radius: 3px;
		white-space: nowrap;
		background: var(--chip-clay);
		color: var(--chip-clay-c);
	}
	.chip.b {
		background: var(--chip-blue);
		color: var(--chip-blue-c);
	}
	.chip.g {
		background: var(--chip-green);
		color: var(--chip-green-c);
	}
	.yields {
		font-family: var(--f-mono);
		font-size: 0.78rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		margin: 1.1rem 0 0;
	}
	.lede {
		font-family: var(--f-serif);
		font-size: 1.16rem;
		line-height: 1.65;
		color: var(--ink);
		max-width: 50rem;
		margin: 1.5rem 0 0;
	}
	.lede p {
		margin: 0;
	}
	.lede.clamped p {
		display: -webkit-box;
		-webkit-line-clamp: 4;
		line-clamp: 4;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.readmore {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--clay-deep);
		background: none;
		border: none;
		border-bottom: 1px solid transparent;
		padding: 0;
		margin-top: 0.7rem;
		cursor: pointer;
	}
	.readmore:hover {
		border-bottom-color: var(--clay);
	}

	/* Favourite ★ + add-to-list. Stacked in the right rail for the no-image default;
	   a horizontal pair riding the yield line when the rail holds the image. */
	.actions {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.actions.inline {
		flex-direction: row;
		align-items: center;
		gap: 0.6rem;
		margin-top: 1.3rem;
	}
	/* Yield heads the ingredients column in the image layout. */
	.yield-lead {
		margin: 0 0 0.85rem;
	}

	/* Recipe image — a bordered editorial plate in the masthead rail (DESIGN §7).
	   Absent for the no-image default, the common case. */
	.recipe-figure {
		margin: 0;
	}
	.recipe-image {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 5;
		object-fit: cover;
		border: var(--border);
		border-radius: 2px;
		background: var(--bg-warm);
	}

	/* Body — ingredients rail + a wide method column fills the desktop width. */
	.body {
		display: grid;
		grid-template-columns: minmax(260px, 320px) 1fr;
		column-gap: 4.5rem;
		align-items: start;
	}
	.label {
		margin-bottom: 1rem;
	}

	.ingredients {
		list-style: none;
		margin: 0;
		padding: 0;
		font-family: var(--f-serif);
		font-size: 1.05rem;
		line-height: 1.4;
	}
	.ingredients li {
		padding: 0.65rem 0;
		border-top: var(--border);
	}
	.ingredients li:first-child {
		border-top: var(--border-strong);
	}

	.method {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.method li {
		display: grid;
		grid-template-columns: 2.5rem 1fr;
		gap: 0.75rem;
		padding: 1rem 0;
		border-top: var(--border);
	}
	.method li:first-child {
		border-top: var(--border-strong);
	}
	.stepno {
		font-family: var(--f-mono);
		font-size: 0.82rem;
		font-weight: 400;
		color: var(--clay);
		padding-top: 0.3rem;
	}
	.steptext {
		font-family: var(--f-serif);
		font-size: 1.12rem;
		line-height: 1.65;
		color: var(--ink);
		max-width: 44rem;
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.15rem;
		color: var(--muted);
		margin: 0;
	}

	/* Provenance — a quiet full-width footer linking back to the book. */
	.prov {
		border-top: var(--border-strong);
		margin-top: 3.5rem;
		padding-top: 1.6rem;
	}
	.provlink {
		display: inline-flex;
		align-items: center;
		gap: 1rem;
		text-decoration: none;
	}
	.provplate {
		flex: none;
		width: 54px;
		aspect-ratio: 2 / 3;
		background: var(--bg-warm);
		border: var(--border);
		border-radius: 2px;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.provcover {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.provplate-title {
		font-family: var(--f-serif);
		font-style: italic;
		font-weight: 300;
		font-size: 0.62rem;
		line-height: 1.2;
		text-align: center;
		padding: 0.3rem;
		color: var(--muted);
	}
	.provmeta {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.provtitle {
		font-family: var(--f-serif);
		font-size: 1.05rem;
		color: var(--ink);
		transition: color 0.18s var(--ease-out);
	}
	.provlink:hover .provtitle {
		color: var(--clay-deep);
	}
	.provauthor {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		color: var(--muted);
	}

	@media (max-width: 900px) {
		.head,
		.masthead.has-image .head {
			grid-template-columns: 1fr;
			row-gap: 1.85rem;
		}
		.actions {
			flex-direction: row;
		}
		/* The hero plate stacks under the title — a gentler landscape crop on phones. */
		.recipe-image {
			aspect-ratio: 3 / 2;
		}
		.body {
			grid-template-columns: 1fr;
			row-gap: 2.75rem;
		}
	}
</style>
