// First-party types + loader for the vendored foliate-js engine.
// The engine itself is untyped JS (see src/lib/vendor/foliate-js/PROVENANCE.md); these interfaces
// cover only the slice EpubReader.svelte uses. Keep them in sync with the pinned upstream commit.

export interface FoliateTOCItem {
	label: string;
	href: string;
	subitems?: FoliateTOCItem[];
}

export interface FoliateRelocateDetail {
	fraction: number;
	/** Canonical location of the current page, for reopening the book where it was left. */
	cfi?: string;
	tocItem?: { label?: string; href?: string };
}

export interface FoliateRenderer {
	setStyles?(css: string): void;
	setAttribute(name: string, value: string): void;
	next(): void;
	/** The renderer's own relocate events carry a `reason` the view-level event strips
	 *  ('page' | 'snap' | 'scroll' for reading movement; 'anchor' | 'navigation' |
	 *  'selection' for jumps and layout re-anchoring). */
	addEventListener(type: 'relocate', listener: (e: Event) => void): void;
}

/** One spine document. `createDocument` parses it without rendering, which is how a
 *  recipe is located in the text without paging through the book. */
export interface FoliateSection {
	createDocument?(): Promise<Document>;
}

export interface FoliateBook {
	toc?: FoliateTOCItem[];
	dir?: string;
	metadata?: Record<string, unknown>;
	sections?: FoliateSection[];
}

export interface FoliateView extends HTMLElement {
	open(book: Blob | File | string): Promise<void>;
	goTo(target: string | number): Promise<unknown>;
	prev(distance?: number): Promise<void>;
	next(distance?: number): Promise<void>;
	goLeft(): Promise<void>;
	goRight(): Promise<void>;
	book: FoliateBook;
	renderer: FoliateRenderer;
	/** The location the view last computed for a relocate (see view.js #onRelocate). */
	lastLocation?: { cfi?: string } | null;
	/** The canonical location of a range within the section at `index`. */
	getCFI(index: number, range: Range): string;
}

/** Dynamically load the vendored engine — registers the `<foliate-view>` custom element.
 *  Kept dynamic so the engine stays off every other route's bundle. */
export async function ensureFoliateView(): Promise<void> {
	await import('$lib/vendor/foliate-js/view.js');
}

/** Whichever of two locations sits later in the book. Null-tolerant, and on an unparseable
 *  CFI falls back to `a` — a resume that lands somewhere beats one that throws. */
export async function furthestCfi(a: string | null, b: string | null): Promise<string | null> {
	if (!a || !b) return a ?? b;
	try {
		const { compare } = await import('$lib/vendor/foliate-js/epubcfi.js');
		return compare(a, b) >= 0 ? a : b;
	} catch (e) {
		console.warn('could not compare reading locations', e);
		return a;
	}
}
