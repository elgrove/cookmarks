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

// Mirrors the RecipeRow / BookDetail wire shapes from GET /api/books/{id} (snake_case).
export const recipeRowSchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	keywords: z.array(z.string())
});

export const bookDetailSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	isbn: z.string().nullable(),
	pubdate: z.string().nullable(),
	description: z.string(),
	recipe_count: z.number().int().nonnegative(),
	has_cover: z.boolean(),
	added: z.string().nullable(),
	recipes: z.array(recipeRowSchema)
});

export type BookDetailResponse = z.infer<typeof bookDetailSchema>;

/** Fetch and validate a single book's detail. `fetchFn` is injectable for SSR/tests. */
export async function fetchBookDetail(
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<BookDetailResponse> {
	const res = await fetchFn(`/api/books/${id}`);
	if (!res.ok) throw new Error(`GET /api/books/${id} → ${res.status}`);
	return bookDetailSchema.parse(await res.json());
}
