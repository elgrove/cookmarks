// Downloading book files for the in-app reader (MY-213).
//
// What each renderer supports, tested against the vendored engine:
// - PDF: pdf.js reads through a `PDFDataRangeTransport` fed by `file.slice()`
//   (see vendor `pdf.js` `makePDF`), so a range-backed shim streams pages over
//   HTTP 206 responses — the first page renders long before the whole book
//   arrives. Needs `Accept-Ranges: bytes` on GET /api/books/{id}/file.
// - EPUB: the ZIP loader (`vendor/view.js` `makeZipLoader`) reads the central
//   directory out of a whole Blob, so the full file downloads first. That path
//   gets byte progress plus a persistent Cache Storage copy, making repeat
//   opens instant.

export type DownloadProgress = {
	loaded: number;
	total: number | null;
};

export type DownloadedBook = {
	blob: Blob;
	total: number | null;
	etag: string | null;
	contentType: string | null;
};

/** MiB with one decimal — the unit the ticket's file-size evidence uses. */
export function formatMiB(bytes: number): string {
	return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

type NetworkInformation = {
	saveData?: boolean;
	effectiveType?: string;
};

function connection(): NetworkInformation | null {
	try {
		const nav = navigator as Navigator & { connection?: NetworkInformation };
		return nav.connection ?? null;
	} catch {
		return null;
	}
}

/** Whether the device asks us not to spend its data — prefetch stays off then. */
export function isMeteredConnection(): boolean {
	const c = connection();
	if (!c) return false;
	if (c.saveData) return true;
	return c.effectiveType === 'slow-2g' || c.effectiveType === '2g';
}

const BOOK_CACHE = 'cookmarks-books-v1';

async function openBookCache(): Promise<Cache | null> {
	try {
		if (typeof caches === 'undefined') return null;
		return await caches.open(BOOK_CACHE);
	} catch {
		return null;
	}
}

export type CachedBook = {
	blob: Blob;
	etag: string | null;
};

/** The stored copy of a book file, if a previous open cached one. */
export async function readCachedBook(url: string): Promise<CachedBook | null> {
	const cache = await openBookCache();
	if (!cache) return null;
	let hit: Response | undefined;
	try {
		hit = await cache.match(url);
	} catch {
		return null;
	}
	if (!hit) return null;
	return { blob: await hit.blob(), etag: hit.headers.get('etag') };
}

/** Keep a downloaded book file for later opens. Never throws — caching is best-effort. */
export async function storeCachedBook(
	url: string,
	blob: Blob,
	init: { etag?: string | null; contentType?: string | null } = {}
): Promise<void> {
	const cache = await openBookCache();
	if (!cache) return;
	const headers = new Headers();
	if (init.etag) headers.set('etag', init.etag);
	if (init.contentType) headers.set('content-type', init.contentType);
	try {
		await cache.put(url, new Response(blob, { headers }));
	} catch {
		// Quota or opaque-response restrictions — the book still opened, so ignore.
	}
}

export type FileProbe = {
	size: number | null;
	etag: string | null;
	contentType: string | null;
	acceptsRanges: boolean;
};

const RANGE_TOTAL = /bytes \d+-\d+\/(\d+)/;

/**
 * Learn a book file's size, ETag and range support without downloading it. A
 * one-byte range reveals the total via Content-Range in a single round trip
 * (HEAD answers 405 on this API, so ranges lead and HEAD is the fallback).
 */
export async function probeFile(
	url: string,
	fetchFn: typeof fetch = fetch
): Promise<FileProbe> {
	try {
		const res = await fetchFn(url, { headers: { Range: 'bytes=0-0' } });
		if (res.status === 206) {
			const match = RANGE_TOTAL.exec(res.headers.get('content-range') ?? '');
			await res.arrayBuffer().catch(() => undefined);
			return {
				size: match ? Number(match[1]) : null,
				etag: res.headers.get('etag'),
				contentType: res.headers.get('content-type'),
				acceptsRanges: true
			};
		}
		const length = res.headers.get('content-length');
		await res.body?.cancel().catch(() => undefined);
		if (res.ok) {
			return {
				size: length !== null && length !== '' ? Number(length) : null,
				etag: res.headers.get('etag'),
				contentType: res.headers.get('content-type'),
				acceptsRanges: false
			};
		}
	} catch {
		// Fall through to the HEAD probe below.
	}
	try {
		const head = await fetchFn(url, { method: 'HEAD' });
		if (head.ok) {
			const length = head.headers.get('content-length');
			return {
				size: length !== null && length !== '' ? Number(length) : null,
				etag: head.headers.get('etag'),
				contentType: head.headers.get('content-type'),
				acceptsRanges: (head.headers.get('accept-ranges') ?? '').includes('bytes')
			};
		}
	} catch {
		// Unreachable — report unknown rather than throwing.
	}
	return { size: null, etag: null, contentType: null, acceptsRanges: false };
}

/** Fetch a whole book file, reporting bytes as they arrive for the progress UI. */
export async function downloadWithProgress(
	url: string,
	onProgress: (progress: DownloadProgress) => void,
	options: { signal?: AbortSignal; fetchFn?: typeof fetch } = {}
): Promise<DownloadedBook> {
	const fetchFn = options.fetchFn ?? fetch;
	const res = await fetchFn(url, options.signal ? { signal: options.signal } : undefined);
	if (!res.ok) throw new Error(`GET ${url} → ${res.status}`);
	const length = res.headers.get('content-length');
	const total = length !== null && length !== '' ? Number(length) : null;
	const etag = res.headers.get('etag');
	const contentType = res.headers.get('content-type');
	if (typeof res.body?.getReader !== 'function') {
		const blob = await res.blob();
		onProgress({ loaded: blob.size, total: total ?? blob.size });
		return { blob, total: total ?? blob.size, etag, contentType };
	}
	const reader = res.body.getReader();
	const chunks: BlobPart[] = [];
	let loaded = 0;
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		chunks.push(value);
		loaded += value.byteLength;
		onProgress({ loaded, total });
	}
	const blob = new Blob(chunks, { type: contentType ?? '' });
	return { blob, total: total ?? blob.size, etag, contentType };
}

/**
 * A Blob-like backed by HTTP ranges for foliate's PDF path. The vendored
 * `makePDF` only ever calls `file.slice(begin, end).arrayBuffer()` (magic
 * sniffing plus the pdf.js range transport), so each page fetch becomes a
 * small 206 request instead of one full download. `arrayBuffer()` stays
 * throwing: anything calling it wants the whole file, which this shim
 * deliberately never holds.
 */
export type RangeBackedFile = {
	name: string;
	type: string;
	size: number;
	slice(begin: number, end?: number): { arrayBuffer(): Promise<ArrayBuffer> };
	arrayBuffer(): Promise<ArrayBuffer>;
};

export function makeRangeBackedFile(
	url: string,
	size: number,
	options: { contentType?: string | null; fetchFn?: typeof fetch } = {}
): RangeBackedFile {
	const fetchFn = options.fetchFn ?? fetch;
	const slice = (begin: number, end?: number) => ({
		async arrayBuffer(): Promise<ArrayBuffer> {
			const stop = end ?? size;
			const res = await fetchFn(url, { headers: { Range: `bytes=${begin}-${stop - 1}` } });
			if (res.status === 206) return res.arrayBuffer();
			// The server ignored the range — slice the full body down instead.
			const full = await res.arrayBuffer();
			return full.slice(begin, stop);
		}
	});
	return {
		name: 'book.pdf',
		type: options.contentType ?? 'application/pdf',
		size,
		slice,
		async arrayBuffer(): Promise<ArrayBuffer> {
			throw new Error('range-backed file: open it through slice(), not arrayBuffer()');
		}
	};
}

/**
 * Warm the book-file cache ahead of the reader — called from the book detail's
 * Read action on hover/focus, never on a metered connection. Best-effort: any
 * failure is swallowed so prefetch can never break the page.
 */
export async function warmBookCache(
	url: string,
	fetchFn: typeof fetch = fetch
): Promise<void> {
	try {
		if (isMeteredConnection()) return;
		const cached = await readCachedBook(url);
		const probe = await probeFile(url, fetchFn);
		if (cached && cached.etag && probe.etag && cached.etag === probe.etag) return;
		if (cached && probe.size === null && probe.etag === null) return;
		const { blob, etag, contentType } = await downloadWithProgress(url, () => undefined, {
			fetchFn
		});
		await storeCachedBook(url, blob, {
			etag: etag ?? probe.etag,
			contentType: contentType ?? probe.contentType
		});
	} catch {
		// Prefetch is invisible work — it must never surface an error.
	}
}
