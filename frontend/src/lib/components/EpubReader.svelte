<script lang="ts">
	import { onMount } from 'svelte';
	import {
		ensureFoliateView,
		furthestCfi,
		type FoliateRelocateDetail,
		type FoliateTOCItem,
		type FoliateView
	} from '$lib/reader/foliate';
	import {
		bookFileUrl,
		fetchRecipeIndex,
		reportReading,
		type ReadingState,
		type RecipeIndexEntry
	} from '$lib/api/books';
	import { toggleFavourite } from '$lib/api/lists';
	import { reportEpubLocation } from '$lib/api/recipes';
	import {
		buildRecipeIndex,
		matchHeading,
		normaliseTitle,
		type RecipeMatch,
		type RecipeNameIndex
	} from '$lib/reader/match';
	import { resolvedTheme, toggleTheme } from '$lib/theme';
	import ReaderChrome, { type TocEntry } from './ReaderChrome.svelte';
	import ReaderNotFound from './ReaderNotFound.svelte';
	import ReaderRecipePanel, { type PanelAnchor } from './ReaderRecipePanel.svelte';

	type Props = {
		bookId: string;
		title: string;
		author: string;
		/** How far the book has been read, either way, if it has been opened before. */
		resume?: ReadingState | null;
		/** Open at this recipe instead of the resume position — a targeted jump from its page. */
		startRecipeId?: string | null;
	};
	let { bookId, title, author, resume = null, startRecipeId = null }: Props = $props();

	let host = $state<HTMLDivElement>();
	let view: FoliateView | null = null;
	// The book's recipes keyed by normalised name, for matching headings as sections render.
	let recipeIndex: RecipeNameIndex | null = null;
	// The same recipes unkeyed — the name index drops duplicate-named recipes, so a
	// targeted id is resolved against the raw list.
	let rawIndex: RecipeIndexEntry[] | null = null;

	let status = $state<'loading' | 'error' | 'ready' | 'not-found'>('loading');
	// The name behind a failed targeted jump (null when the id wasn't in the index at all).
	let missedName = $state<string | null>(null);
	let toc = $state<TocEntry[]>([]);
	let currentHref = $state<string | null>(null);
	let progress = $state(0);
	let fontScale = $state(1);
	// The save-to-list popover for a matched recipe, opened from its injected `+`.
	let panel = $state<{ recipe: RecipeMatch; anchor: PanelAnchor } | null>(null);

	// Page-ground / ink / link colours injected into the book's own (cross-document) iframe,
	// since the app's CSS custom properties don't reach it. Values track DESIGN.md tokens.
	const THEME_COLOURS = {
		light: { bg: '#fafaf5', ink: '#1e2025', link: '#155239', clay: '#1f6f50', line: '#c9c6b8' },
		dark: { bg: '#16181c', ink: '#eceee7', link: '#67c096', clay: '#46a87d', line: '#3c4148' }
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
		// The controls we inject next to matched recipe titles: a circular star button mirroring
		// the app's FavouriteToggle (clay star, hairline border that turns clay when hovered or
		// saved, transparent fill), and a matching `+` circle that opens the save-to-list popover.
		const fav = `
			.cm-fav, .cm-plus { box-sizing: border-box; display: inline-flex; align-items: center;
				justify-content: center; width: 1.7em; height: 1.7em; padding: 0;
				margin-inline-start: 0.75em; vertical-align: middle; font-size: 0.8rem;
				font-style: normal; text-transform: none; line-height: 1; cursor: pointer;
				border-radius: 50%; border: 1.5px solid ${c.line}; background: transparent;
				color: ${c.clay} !important; -webkit-text-fill-color: ${c.clay};
				transition: border-color 0.18s ease, transform 0.12s ease; }
			.cm-fav:hover, .cm-plus:hover { border-color: ${c.clay}; transform: scale(1.08); }
			.cm-fav.is-fav { border-color: ${c.clay}; }
			.cm-fav[disabled] { opacity: 0.5; cursor: default; }
			.cm-plus { margin-inline-start: 0.4em; }
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

	/** An in-content element's rect translated to app-viewport coords (content iframe offset added). */
	function appAnchor(el: HTMLElement, doc: Document): PanelAnchor {
		const r = el.getBoundingClientRect();
		const frame = doc.defaultView?.frameElement?.getBoundingClientRect();
		return { x: r.left + (frame?.left ?? 0), y: r.top + (frame?.top ?? 0), w: r.width, h: r.height };
	}

	// The latest injected star's re-render per recipe, so a favourite change made in the
	// popover updates the in-book star too.
	const starSync = new Map<string, () => void>();

	// Cookbook EPUBs rarely use semantic headings — titles are often bold lines (e.g. Calibre's
	// `<p><b>…</b></p>`) or class-styled paragraphs — so candidates are headings, bold elements
	// and short paragraphs, with the looser (non-heading) ones held to an exact name match.
	const TITLE_CANDIDATES = 'h1, h2, h3, h4, h5, h6, b, strong, p';

	/** Match one candidate element against the recipe index, or null. Link-wrapped text is a
	 *  cross-reference (contents lines, "see also"), never the recipe's own title. */
	function matchTitleElement(el: HTMLElement, index: RecipeNameIndex): RecipeMatch | null {
		if (el.closest('a') || el.querySelector('a[href]')) return null;
		const text = (el.textContent ?? '').trim();
		if (text.length < 3 || text.length > 90) return null;
		const isHeading = el.matches('h1, h2, h3, h4, h5, h6');
		return isHeading ? matchHeading(text, index) : (index.get(normaliseTitle(text)) ?? null);
	}

	// As each section renders, find the lines that name one of the book's recipes and inject the
	// controls right after the title. Runs in the (same-origin) content document.
	function injectControls(doc: Document) {
		const index = recipeIndex;
		if (!index) return;
		doc.querySelectorAll(TITLE_CANDIDATES).forEach((node) => {
			const el = node as HTMLElement;
			if (el.dataset.cmFav) return; // already processed
			if (el.querySelector('[data-cm-fav]') || el.closest('[data-cm-fav]')) return; // nested dup
			const match = matchTitleElement(el, index);
			if (!match) return;
			el.dataset.cmFav = match.id;

			const btn = doc.createElement('button');
			btn.className = 'cm-fav';
			btn.type = 'button';
			const render = () => {
				const fav = match.isFavourite;
				btn.textContent = fav ? '★' : '☆';
				btn.setAttribute('aria-pressed', String(fav));
				btn.setAttribute(
					'aria-label',
					`${fav ? 'Remove' : 'Save'} ${match.name} ${fav ? 'from' : 'to'} favourites`
				);
				btn.classList.toggle('is-fav', fav);
			};
			render();
			starSync.set(match.id, render);
			btn.addEventListener('click', (ev) => {
				ev.preventDefault();
				ev.stopPropagation();
				btn.disabled = true;
				toggleFavourite(match.id)
					.then((next) => {
						match.isFavourite = next; // keep the index in sync if the section re-renders
						render();
					})
					.catch((e) => console.error('favourite toggle failed', e))
					.finally(() => {
						btn.disabled = false;
					});
			});

			const plus = doc.createElement('button');
			plus.className = 'cm-plus';
			plus.type = 'button';
			plus.textContent = '+';
			plus.setAttribute('aria-label', `Save ${match.name} to a list`);
			plus.addEventListener('click', (ev) => {
				ev.preventDefault();
				ev.stopPropagation();
				panel = { recipe: match, anchor: appAnchor(plus, doc) };
			});

			el.append(btn, plus);
		});
	}

	// Re-inject content styles whenever text size or theme changes (once the view exists).
	$effect(() => {
		void fontScale;
		void $resolvedTheme;
		if (view && status === 'ready') applyStyles();
	});

	// The section on screen, so the recipes its pages carry past can be reported.
	let currentDoc: Document | null = null;

	/** The furthest recipe the current page has reached: matched headings sit in the
	 *  content document, and in paginated flow anything on or behind the current page
	 *  has a rect left of the viewport's right edge. */
	function reachedRecipeId(): string | null {
		const doc = currentDoc;
		const width = doc?.defaultView?.innerWidth;
		if (!doc || !width) return null;
		let reached: string | null = null;
		for (const el of doc.querySelectorAll<HTMLElement>('[data-cm-fav]')) {
			if (el.getBoundingClientRect().left < width) reached = el.dataset.cmFav ?? reached;
		}
		return reached;
	}

	/** A one-recipe index, matched the same way headings are as they render, so a recipe
	 *  the book titles slightly differently ("Plantain" for "Plantain (fry)") resolves. */
	const wantedIndex = (name: string): RecipeNameIndex =>
		buildRecipeIndex([{ id: '', name, is_favourite: false, epub_cfi: null }]);

	/** Find a recipe in the book's own text, for opening the pages where the recipe walk
	 *  left off. Sections are parsed, not rendered, and the scan stops at the first hit;
	 *  a recipe whose title the book doesn't spell the same way simply isn't found. */
	async function locateRecipe(el: FoliateView, name: string): Promise<string | null> {
		const wanted = wantedIndex(name);
		const sections = el.book?.sections ?? [];
		for (const [index, section] of sections.entries()) {
			if (!section.createDocument) continue;
			const doc = await section.createDocument();
			const heading = [...doc.querySelectorAll(TITLE_CANDIDATES)].find((node) =>
				matchTitleElement(node as HTMLElement, wanted)
			);
			if (!heading) continue;
			const range = doc.createRange();
			range.selectNodeContents(heading);
			return el.getCFI(index, range);
		}
		return null;
	}

	/** Scan the sections for a recipe and cache what came back — a miss included, so it is
	 *  recorded as checked-and-absent and its own page can say so before the click. */
	async function scanAndCache(el: FoliateView, entry: RecipeIndexEntry): Promise<string | null> {
		const cfi = await locateRecipe(el, entry.name);
		reportEpubLocation(entry.id, cfi).catch((e) =>
			console.warn('could not cache the reader position', e)
		);
		return cfi;
	}

	/** Whether the section now on screen names this recipe. */
	function pagesName(name: string): boolean {
		const doc = currentDoc;
		if (!doc) return false;
		const wanted = wantedIndex(name);
		return [...doc.querySelectorAll(TITLE_CANDIDATES)].some((node) =>
			matchTitleElement(node as HTMLElement, wanted)
		);
	}

	/** Open the pages at a recipe, returning where it landed (null if the book doesn't
	 *  name it). The cached position is only trusted if the section it opens still names
	 *  the recipe: a re-synced EPUB can leave one that resolves but points at other text,
	 *  and re-scanning on that rare miss is cheaper than invalidating the cache wholesale.
	 *  A rejected jump leaves the pages where it landed, so callers that don't go on to
	 *  open somewhere else must move off it before reading resumes. */
	async function openAtRecipe(el: FoliateView, entry: RecipeIndexEntry): Promise<string | null> {
		if (entry.epub_cfi) {
			const landed = await el
				.goTo(entry.epub_cfi)
				.then(() => pagesName(entry.name))
				.catch(() => false);
			if (landed) return entry.epub_cfi;
		}
		const cfi = await scanAndCache(el, entry);
		if (cfi) await el.goTo(cfi).catch(() => el.renderer.next());
		return cfi;
	}

	// Reading is reported back as the reader moves, at most once every few seconds, with
	// the latest flushed when the reader closes.
	const SAVE_INTERVAL_MS = 5000;
	let pending: { recipe_id: string | null; location: string | null } | null = null;
	let lastSaved = 0;

	function flushPosition() {
		if (!pending) return;
		const { recipe_id, location } = pending;
		pending = null;
		lastSaved = Date.now();
		reportReading(bookId, { mode: 'book', recipe_id, location }).catch((e) =>
			console.warn('could not report reading position', e)
		);
	}

	function recordPosition(location: string | null) {
		pending = { recipe_id: reachedRecipeId(), location };
		if (Date.now() - lastSaved >= SAVE_INTERVAL_MS) flushPosition();
	}

	function onKeydown(e: KeyboardEvent) {
		if (status !== 'ready') return;
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
					.then((entries) => {
						rawIndex = entries;
						return buildRecipeIndex(entries);
					})
					.catch((e) => {
						console.warn('recipe index unavailable; matching disabled', e);
						return null;
					});
				const res = await fetch(bookFileUrl(bookId));
				if (!res.ok) throw new Error(`GET book file → ${res.status}`);
				const blob = await res.blob();
				if (cancelled || !host) return;

				// foliate's loader sniffs the filename (e.g. .cbz), so a named File is required —
				// a bare Blob would throw in makeBook.
				const file = new File([blob], 'book', { type: blob.type });
				const el = document.createElement('foliate-view') as unknown as FoliateView;
				host.append(el);
				view = el;

				el.addEventListener('relocate', (e: Event) => {
					const detail = (e as CustomEvent<FoliateRelocateDetail>).detail ?? ({} as FoliateRelocateDetail);
					if (typeof detail.fraction === 'number') progress = detail.fraction;
					currentHref = detail.tocItem?.href ?? currentHref;
					panel = null; // a page turn leaves the popover's anchor stale
				});
				el.addEventListener('load', (e: Event) => {
					const detail = (e as CustomEvent<{ doc: Document }>).detail;
					if (!detail?.doc) return;
					currentDoc = detail.doc;
					injectControls(detail.doc);
				});

				// Ready before open() renders the first section, so its headings get matched too.
				recipeIndex = await indexPromise;
				await el.open(file);
				if (cancelled) return;

				// Only genuine reading movement records the position — the same reasons foliate
				// itself treats as history-worthy. Jumps and layout re-anchoring ('anchor',
				// 'navigation', 'selection') are not reading, so a targeted arrival, the resume
				// landing and setStyles re-layouts all leave the stored position alone. The
				// reason only exists on the renderer's own relocate; the view-level event
				// strips it.
				el.renderer.addEventListener('relocate', (e: Event) => {
					const reason = (e as CustomEvent<{ reason?: string }>).detail?.reason;
					// The not-found overlay hides the pages, so nothing turned behind it counts.
					if (status !== 'ready') return;
					if (reason === 'page' || reason === 'snap' || reason === 'scroll')
						recordPosition(el.lastLocation?.cfi ?? null);
				});

				el.renderer.setAttribute('flow', 'paginated');
				el.renderer.setAttribute('gap', '6%');
				el.renderer.setAttribute('max-inline-size', '38rem');
				el.renderer.setAttribute('max-column-count', '2');
				applyStyles();
				toc = flattenToc(el.book?.toc);
				if (startRecipeId) {
					// A targeted jump from the recipe's own page: it wins over the resume
					// position, and a miss lands on the not-found state, never a random page.
					const entry = rawIndex?.find((r) => r.id === startRecipeId) ?? null;
					const cfi = entry ? await openAtRecipe(el, entry) : null;
					if (cancelled) return;
					if (!cfi) {
						missedName = entry?.name ?? null;
						status = 'not-found';
						return;
					}
				} else {
					// One position, either way in: the pages resume at whichever is further through
					// the book — the page they were left on, or the recipe the walk reached.
					// The anchor is scanned for rather than taken from the cache: it is weighed
					// against the stored page and the further of the two wins, so an unverified
					// cached position that a re-synced EPUB has left pointing deeper into the
					// book would take the reader past where they actually got to.
					const anchor = resume?.anchor ?? null;
					const anchorEntry = anchor
						? (rawIndex?.find((r) => r.id === anchor.id) ?? null)
						: null;
					const anchorCfi = anchorEntry
						? await scanAndCache(el, anchorEntry)
						: anchor
							? await locateRecipe(el, anchor.name)
							: null;
					const target = await furthestCfi(resume?.location ?? null, anchorCfi);
					if (target) await el.goTo(target).catch(() => el.renderer.next());
					else el.renderer.next(); // render the first page
				}
				status = 'ready';
			} catch (err) {
				if (!cancelled) {
					console.error('failed to open epub', err);
					status = 'error';
				}
			}
		})();

		window.addEventListener('keydown', onKeydown);
		window.addEventListener('pagehide', flushPosition);
		return () => {
			cancelled = true;
			flushPosition();
			window.removeEventListener('keydown', onKeydown);
			window.removeEventListener('pagehide', flushPosition);
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
			{:else if status === 'not-found'}
				<ReaderNotFound
					recipeName={missedName}
					recipeHref={`/recipes/${startRecipeId}`}
					onOpenAtStart={() => {
						// Explicitly the book's first section: a rejected cached position may have
						// left the pages parked somewhere arbitrary, and paging on from there would
						// record that as the reading position.
						status = 'ready';
						view?.goTo(0).catch(() => view?.renderer.next());
					}}
				/>
			{:else}
				<p class="msg">This book couldn’t be opened.</p>
				<a class="back" href={`/books/${bookId}`}>← Back to book</a>
			{/if}
		</div>
	{/if}
</ReaderChrome>

{#if panel}
	<ReaderRecipePanel
		recipeId={panel.recipe.id}
		recipeName={panel.recipe.name}
		anchor={panel.anchor}
		onClose={() => (panel = null)}
		onFavouriteChange={(fav) => {
			if (!panel) return;
			panel.recipe.isFavourite = fav;
			starSync.get(panel.recipe.id)?.();
		}}
	/>
{/if}

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
		color: var(--accent-deep);
		text-decoration: none;
		border-bottom: 1px solid transparent;
	}
	.back:hover {
		border-bottom-color: var(--accent);
	}
</style>
