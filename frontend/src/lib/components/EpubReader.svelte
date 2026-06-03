<script lang="ts">
	import { onMount } from 'svelte';
	import {
		ensureFoliateView,
		type FoliateRelocateDetail,
		type FoliateTOCItem,
		type FoliateView
	} from '$lib/reader/foliate';
	import { epubUrl, fetchRecipeIndex } from '$lib/api/books';
	import { toggleFavourite } from '$lib/api/lists';
	import {
		buildRecipeIndex,
		matchHeading,
		normaliseTitle,
		type RecipeNameIndex
	} from '$lib/reader/match';
	import { resolvedTheme, toggleTheme } from '$lib/theme';
	import ReaderChrome, { type TocEntry } from './ReaderChrome.svelte';

	type Props = { bookId: string; title: string; author: string };
	let { bookId, title, author }: Props = $props();

	let host = $state<HTMLDivElement>();
	let view: FoliateView | null = null;
	// The book's recipes keyed by normalised name, for matching headings as sections render.
	let recipeIndex: RecipeNameIndex | null = null;

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let toc = $state<TocEntry[]>([]);
	let currentHref = $state<string | null>(null);
	let progress = $state(0);
	let fontScale = $state(1);

	// Page-ground / ink / link colours injected into the book's own (cross-document) iframe,
	// since the app's CSS custom properties don't reach it. Values track DESIGN.md tokens.
	const THEME_COLOURS = {
		light: { bg: '#faf9f5', ink: '#141413', link: '#c2613f', clay: '#d97757', line: '#d8d4c6' },
		dark: { bg: '#14181e', ink: '#eef1f6', link: '#ef9e7d', clay: '#df8460', line: '#354050' }
	} as const;

	// Elements whose colour the book's own stylesheet typically sets explicitly — so in dark mode
	// we must override them (with !important) or text stays dark-on-dark.
	const TEXT_SELECTOR =
		'body, p, li, h1, h2, h3, h4, h5, h6, span, div, td, th, dd, dt, blockquote, figure, figcaption, em, strong, b, i, small';

	function contentCss(scale: number, theme: 'light' | 'dark'): string {
		const c = THEME_COLOURS[theme];
		const common = `
			html { color-scheme: ${theme}; font-size: ${Math.round(scale * 100)}%; }
			p, li, blockquote, dd { line-height: 1.6; }
		`;
		// The save-to-favourites control we inject next to matched recipe titles: a circular star
		// button mirroring the app's FavouriteToggle — clay star, hairline border that turns clay
		// when hovered or saved, transparent fill. Star-only so it stays small against the title.
		const fav = `
			.cm-fav { box-sizing: border-box; display: inline-flex; align-items: center;
				justify-content: center; width: 1.7em; height: 1.7em; padding: 0;
				margin-inline-start: 0.75em; vertical-align: middle; font-size: 0.8rem;
				font-style: normal; text-transform: none; line-height: 1; cursor: pointer;
				border-radius: 50%; border: 1.5px solid ${c.line}; background: transparent;
				color: ${c.clay} !important; -webkit-text-fill-color: ${c.clay};
				transition: border-color 0.18s ease, transform 0.12s ease; }
			.cm-fav:hover { border-color: ${c.clay}; transform: scale(1.08); }
			.cm-fav.is-fav { border-color: ${c.clay}; }
			.cm-fav[disabled] { opacity: 0.5; cursor: default; }
		`;
		if (theme === 'light') {
			return `
				${common}
				html, body { background: ${c.bg}; color: ${c.ink}; }
				a:link, a:visited { color: ${c.link}; }
				${fav}
			`;
		}
		// Dark: force the page ground, text colour and links, since the book's own rules win on
		// specificity. Backgrounds are cleared so the book doesn't paint light panels behind text.
		return `
			${common}
			html, body { background: ${c.bg} !important; }
			${TEXT_SELECTOR} { color: ${c.ink} !important; background-color: transparent !important; }
			a:link, a:visited { color: ${c.link} !important; }
			${fav}
		`;
	}

	function flattenToc(items: FoliateTOCItem[] | undefined, depth = 0, acc: TocEntry[] = []): TocEntry[] {
		for (const item of items ?? []) {
			const href = item.href ?? '';
			if (href) acc.push({ label: (item.label ?? '').trim() || 'Untitled', href, depth });
			if (item.subitems?.length) flattenToc(item.subitems, depth + 1, acc);
		}
		return acc;
	}

	function applyStyles() {
		view?.renderer.setStyles?.(contentCss(fontScale, $resolvedTheme));
	}

	// As each section renders, find the lines that name one of the book's recipes and inject a
	// save-to-favourites pill right after the title. Runs in the (same-origin) content document.
	// Cookbook EPUBs rarely use semantic headings — titles are often bold lines (e.g. Calibre's
	// `<p><b>…</b></p>`) — so we consider headings *and* bold elements, exclude cross-reference
	// links, and require an exact name match on the (looser) bold candidates to avoid false hits.
	function injectFavourites(doc: Document) {
		const index = recipeIndex;
		if (!index) return;
		doc.querySelectorAll('h1, h2, h3, h4, h5, h6, b, strong').forEach((node) => {
			const el = node as HTMLElement;
			if (el.dataset.cmFav) return; // already processed
			if (el.closest('a')) return; // a linked title is a cross-reference, not the recipe
			if (el.querySelector('[data-cm-fav]') || el.closest('[data-cm-fav]')) return; // nested dup
			const text = (el.textContent ?? '').trim();
			if (text.length < 3 || text.length > 90) return;
			const isHeading = el.matches('h1, h2, h3, h4, h5, h6');
			const match = isHeading ? matchHeading(text, index) : (index.get(normaliseTitle(text)) ?? null);
			if (!match) return;
			el.dataset.cmFav = match.id;

			const btn = doc.createElement('button');
			btn.className = 'cm-fav';
			btn.type = 'button';
			let fav = match.isFavourite;
			const render = () => {
				btn.textContent = fav ? '★' : '☆';
				btn.setAttribute('aria-pressed', String(fav));
				btn.setAttribute(
					'aria-label',
					`${fav ? 'Remove' : 'Save'} ${match.name} ${fav ? 'from' : 'to'} favourites`
				);
				btn.classList.toggle('is-fav', fav);
			};
			render();
			btn.addEventListener('click', (ev) => {
				ev.preventDefault();
				ev.stopPropagation();
				btn.disabled = true;
				toggleFavourite(match.id)
					.then((next) => {
						fav = next;
						match.isFavourite = next; // keep the index in sync if the section re-renders
						render();
					})
					.catch((e) => console.error('favourite toggle failed', e))
					.finally(() => {
						btn.disabled = false;
					});
			});
			el.append(btn);
		});
	}

	// Re-inject content styles whenever text size or theme changes (once the view exists).
	$effect(() => {
		void fontScale;
		void $resolvedTheme;
		if (view && status === 'ready') applyStyles();
	});

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'ArrowLeft') view?.prev();
		else if (e.key === 'ArrowRight') view?.next();
	}

	onMount(() => {
		let cancelled = false;

		(async () => {
			try {
				await ensureFoliateView(); // registers the <foliate-view> custom element
				// Fetch the book's recipe index alongside the EPUB; failure just disables matching.
				const indexPromise = fetchRecipeIndex(bookId)
					.then(buildRecipeIndex)
					.catch((e) => {
						console.warn('recipe index unavailable; matching disabled', e);
						return null;
					});
				const res = await fetch(epubUrl(bookId));
				if (!res.ok) throw new Error(`GET epub → ${res.status}`);
				const blob = await res.blob();
				if (cancelled || !host) return;

				// foliate's loader sniffs the filename (e.g. .cbz), so a named File is required —
				// a bare Blob would throw in makeBook.
				const file = new File([blob], 'book.epub', { type: 'application/epub+zip' });
				const el = document.createElement('foliate-view') as unknown as FoliateView;
				host.append(el);
				view = el;

				el.addEventListener('relocate', (e: Event) => {
					const detail = (e as CustomEvent<FoliateRelocateDetail>).detail ?? ({} as FoliateRelocateDetail);
					if (typeof detail.fraction === 'number') progress = detail.fraction;
					currentHref = detail.tocItem?.href ?? currentHref;
				});
				el.addEventListener('load', (e: Event) => {
					const detail = (e as CustomEvent<{ doc: Document }>).detail;
					if (detail?.doc) injectFavourites(detail.doc);
				});

				// Ready before open() renders the first section, so its headings get matched too.
				recipeIndex = await indexPromise;
				await el.open(file);
				if (cancelled) return;

				el.renderer.setAttribute('flow', 'paginated');
				el.renderer.setAttribute('gap', '6%');
				el.renderer.setAttribute('max-inline-size', '38rem');
				el.renderer.setAttribute('max-column-count', '2');
				applyStyles();
				toc = flattenToc(el.book?.toc);
				el.renderer.next(); // render the first page
				status = 'ready';
			} catch (err) {
				if (!cancelled) {
					console.error('failed to open epub', err);
					status = 'error';
				}
			}
		})();

		window.addEventListener('keydown', onKeydown);
		return () => {
			cancelled = true;
			window.removeEventListener('keydown', onKeydown);
			view?.remove();
			view = null;
		};
	});
</script>

<ReaderChrome
	{title}
	{author}
	backHref={`/books/${bookId}`}
	{toc}
	{currentHref}
	{progress}
	{fontScale}
	theme={$resolvedTheme}
	onSelectToc={(href) => view?.goTo(href)}
	onPrev={() => view?.prev()}
	onNext={() => view?.next()}
	onFontDec={() => (fontScale = Math.max(0.6, Math.round((fontScale - 0.1) * 10) / 10))}
	onFontInc={() => (fontScale = Math.min(2, Math.round((fontScale + 0.1) * 10) / 10))}
	onToggleTheme={toggleTheme}
>
	<div class="host" bind:this={host}></div>

	{#if status !== 'ready'}
		<div class="overlay" class:error={status === 'error'}>
			{#if status === 'loading'}
				<p class="msg">Opening the book…</p>
			{:else}
				<p class="msg">This book couldn’t be opened.</p>
				<a class="back" href={`/books/${bookId}`}>← Back to book</a>
			{/if}
		</div>
	{/if}
</ReaderChrome>

<style>
	.host {
		width: 100%;
		height: 100%;
	}
	.host :global(foliate-view) {
		display: block;
		width: 100%;
		height: 100%;
		background: var(--bg);
	}

	.overlay {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1.1rem;
		background: var(--bg);
	}
	.msg {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		margin: 0;
	}
	.overlay.error .msg {
		color: var(--ink);
	}
	.back {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		color: var(--clay-deep);
		text-decoration: none;
		border-bottom: 1px solid transparent;
	}
	.back:hover {
		border-bottom-color: var(--clay);
	}
</style>
