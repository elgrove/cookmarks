import { z } from 'zod';

// A book on the caller's reading queue (also the home "Up next" strip shape).
export const queuedBookSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	has_cover: z.boolean(),
	recipe_count: z.number().int().nonnegative()
});

export const queueStateSchema = z.object({ queued: z.boolean() });

export const readingQueueResponseSchema = z.array(queuedBookSchema);

export type QueuedBook = z.infer<typeof queuedBookSchema>;
export type QueueState = z.infer<typeof queueStateSchema>;

/** The caller's queue, newest-queued first. `fetchFn` is injectable for tests. */
export async function fetchReadingQueue(fetchFn: typeof fetch = fetch): Promise<QueuedBook[]> {
	const res = await fetchFn('/api/reading-queue');
	if (!res.ok) throw new Error(`GET /api/reading-queue → ${res.status}`);
	return readingQueueResponseSchema.parse(await res.json());
}

/** Add the book to the caller's queue (idempotent). */
export async function queueBook(bookId: string, fetchFn: typeof fetch = fetch): Promise<QueueState> {
	const res = await fetchFn(`/api/books/${bookId}/queue`, { method: 'PUT' });
	if (!res.ok) throw new Error(`PUT /api/books/${bookId}/queue → ${res.status}`);
	return queueStateSchema.parse(await res.json());
}

/** Remove the book from the caller's queue (idempotent). */
export async function unqueueBook(
	bookId: string,
	fetchFn: typeof fetch = fetch
): Promise<QueueState> {
	const res = await fetchFn(`/api/books/${bookId}/queue`, { method: 'DELETE' });
	if (!res.ok) throw new Error(`DELETE /api/books/${bookId}/queue → ${res.status}`);
	return queueStateSchema.parse(await res.json());
}
