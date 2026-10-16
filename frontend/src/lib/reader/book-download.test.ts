import { describe, expect, it, vi } from 'vitest';
import {
	downloadWithProgress,
	formatMiB,
	isMeteredConnection,
	makeRangeBackedFile,
	probeFile,
	warmBookCache
} from './book-download';

const stubFetch = (res: Response): typeof fetch =>
	(async () => res) as unknown as typeof fetch;

describe('formatMiB', () => {
	it('formats bytes as MiB with one decimal', () => {
		expect(formatMiB(54.9 * 1024 * 1024)).toBe('54.9 MiB');
		expect(formatMiB(0)).toBe('0.0 MiB');
	});
});

describe('isMeteredConnection', () => {
	it('is unmetered when the device exposes no connection info', () => {
		expect(isMeteredConnection()).toBe(false);
	});
});

describe('probeFile', () => {
	it('reads size, etag and range support from a one-byte range', async () => {
		const fetchFn = (async () => {
			return new Response(new Uint8Array([0x50]), {
				status: 206,
				headers: {
					'content-range': 'bytes 0-0/57671680',
					etag: '"abc123"',
					'content-type': 'application/epub+zip'
				}
			});
		}) as unknown as typeof fetch;
		await expect(probeFile('/api/books/1/file', fetchFn)).resolves.toEqual({
			size: 57671680,
			etag: '"abc123"',
			contentType: 'application/epub+zip',
			acceptsRanges: true,
			status: 206
		});
	});

	it('reports no range support when the server answers the range with 200', async () => {
		const fetchFn = (async () => {
			const res = new Response('hello', {
				headers: { 'content-length': '5', 'content-type': 'application/pdf' }
			});
			// Undici Response bodies must be cancelled, not left hanging.
			void res.body?.cancel().catch(() => undefined);
			return res;
		}) as unknown as typeof fetch;
		const probe = await probeFile('/api/books/1/file', fetchFn);
		expect(probe.acceptsRanges).toBe(false);
		expect(probe.size).toBe(5);
		expect(probe.status).toBe(200);
	});

	it('falls back to HEAD when ranges fail', async () => {
		const fetchFn = (async (_url: string, init?: RequestInit) => {
			if (init?.method === 'HEAD') {
				return new Response(null, {
					headers: {
						'content-length': '50331648',
						etag: '"pdf-etag"',
						'content-type': 'application/pdf',
						'accept-ranges': 'bytes'
					}
				});
			}
			throw new TypeError('range unsupported');
		}) as unknown as typeof fetch;
		await expect(probeFile('/api/books/1/file', fetchFn)).resolves.toEqual({
			size: 50331648,
			etag: '"pdf-etag"',
			contentType: 'application/pdf',
			acceptsRanges: true,
			status: 200
		});
	});

	it('reports the HTTP status when the book is gone, so a stale cache is not trusted', async () => {
		const fetchFn = (async () => new Response(null, { status: 404 })) as unknown as typeof fetch;
		await expect(probeFile('/api/books/1/file', fetchFn)).resolves.toEqual({
			size: null,
			etag: null,
			contentType: null,
			acceptsRanges: false,
			status: 404
		});
	});

	it('reports unknown rather than throwing when the server is unreachable', async () => {
		const fetchFn = (async () => {
			throw new TypeError('offline');
		}) as unknown as typeof fetch;
		await expect(probeFile('/api/books/1/file', fetchFn)).resolves.toEqual({
			size: null,
			etag: null,
			contentType: null,
			acceptsRanges: false,
			status: null
		});
	});
});

describe('downloadWithProgress', () => {
	it('reports bytes as they arrive and returns the blob', async () => {
		const body = 'x'.repeat(100);
		const seen: number[] = [];
		const fetchFn = stubFetch(
			new Response(body, {
				headers: { 'content-length': String(body.length), 'content-type': 'application/pdf' }
			})
		);
		const { blob, total } = await downloadWithProgress(
			'/api/books/1/file',
			({ loaded }) => seen.push(loaded),
			{ fetchFn }
		);
		expect(blob.size).toBe(100);
		expect(total).toBe(100);
		expect(seen.length).toBeGreaterThan(0);
		expect(seen[seen.length - 1]).toBe(100);
	});

	it('throws on an HTTP error', async () => {
		await expect(
			downloadWithProgress('/api/books/1/file', () => undefined, {
				fetchFn: stubFetch(new Response(null, { status: 404 }))
			})
		).rejects.toThrow('404');
	});
});

describe('makeRangeBackedFile', () => {
	const pdfMagic = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]); // %PDF-

	it('fetches slices as byte ranges', async () => {
		const seen: string[] = [];
		const fetchFn = (async (_url: string, init?: RequestInit) => {
			const headers = init?.headers as Record<string, string>;
			seen.push(headers.Range);
			return new Response(pdfMagic, { status: 206 });
		}) as unknown as typeof fetch;
		const file = makeRangeBackedFile('/api/books/1/file', 50331648, { fetchFn });
		expect(file.size).toBe(50331648);
		const bytes = new Uint8Array(await file.slice(0, 5).arrayBuffer());
		expect(seen).toEqual(['bytes=0-4']);
		expect(bytes).toEqual(pdfMagic);
	});

	it('slices the full body down when the server ignores ranges', async () => {
		const full = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
		const fetchFn = stubFetch(new Response(full, { status: 200 }));
		const file = makeRangeBackedFile('/api/books/1/file', full.length, { fetchFn });
		const bytes = new Uint8Array(await file.slice(2, 5).arrayBuffer());
		expect(bytes).toEqual(new Uint8Array([3, 4, 5]));
	});

	it('throws rather than slicing an error page', async () => {
		const fetchFn = stubFetch(new Response('no such book', { status: 404 }));
		const file = makeRangeBackedFile('/api/books/1/file', 100, { fetchFn });
		await expect(file.slice(0, 5).arrayBuffer()).rejects.toThrow('404');
	});
});

describe('warmBookCache', () => {
	it('never throws, even offline', async () => {
		const fetchFn = (async () => {
			throw new TypeError('offline');
		}) as unknown as typeof fetch;
		await expect(warmBookCache('/api/books/1/file', fetchFn)).resolves.toBeUndefined();
	});

	it('does not fetch on a metered connection', async () => {
		const fetchFn = vi.fn() as unknown as typeof fetch;
		const nav = navigator as Navigator & { connection?: unknown };
		const original = nav.connection;
		Object.defineProperty(navigator, 'connection', {
			value: { saveData: true },
			configurable: true
		});
		try {
			await warmBookCache('/api/books/1/file', fetchFn);
		} finally {
			Object.defineProperty(navigator, 'connection', {
				value: original,
				configurable: true
			});
		}
		expect(fetchFn).not.toHaveBeenCalled();
	});
});
