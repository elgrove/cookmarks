import { z } from 'zod';

// Mirrors the BookSummary wire shape from GET /api/books (snake_case).
export const bookSummarySchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	recipe_count: z.number().int().nonnegative(),
	has_cover: z.boolean(),
	pubdate: z.string().nullable()
});

export const booksResponseSchema = z.array(bookSummarySchema);

export type BookSummary = z.infer<typeof bookSummarySchema>;

/** Fetch and validate the books library. `fetchFn` is injectable for SSR/tests. */
export async function fetchBooks(fetchFn: typeof fetch = fetch): Promise<BookSummary[]> {
	const res = await fetchFn('/api/books');
	if (!res.ok) throw new Error(`GET /api/books → ${res.status}`);
	return booksResponseSchema.parse(await res.json());
}
