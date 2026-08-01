import { z } from 'zod';

// Mirrors the BookSummary wire shape from GET /api/books (snake_case).
export const bookSummarySchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	recipe_count: z.number().int().nonnegative(),
	has_cover: z.boolean(),
	pubdate: z.string().nullable(),
	keywords: z.array(z.string())
});

export const booksResponseSchema = z.array(bookSummarySchema);

export type BookSummary = z.infer<typeof bookSummarySchema>;

/** Fetch and validate the books library. `fetchFn` is injectable for SSR/tests. */
export async function fetchBooks(fetchFn: typeof fetch = fetch): Promise<BookSummary[]> {
	const res = await fetchFn('/api/books');
	if (!res.ok) throw new Error(`GET /api/books → ${res.status}`);
	return booksResponseSchema.parse(await res.json());
}

// Mirrors the BookFilter wire shape from GET /api/books/filters (snake_case): the
// minimal id/title/author the recipes-search controls need, with no recipe-count
// aggregation behind it.
export const bookFilterSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string()
});

export const bookFiltersResponseSchema = z.array(bookFilterSchema);

export type BookFilter = z.infer<typeof bookFilterSchema>;

/** Fetch the lightweight book list for the recipes-search filter controls (id,
 *  title, author only). `fetchFn` is injectable for SSR/tests. */
export async function fetchBookFilters(fetchFn: typeof fetch = fetch): Promise<BookFilter[]> {
	const res = await fetchFn('/api/books/filters');
	if (!res.ok) throw new Error(`GET /api/books/filters → ${res.status}`);
	return bookFiltersResponseSchema.parse(await res.json());
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
	has_epub: z.boolean(),
	added: z.string().nullable(),
	keywords: z.array(z.string()),
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

/** Delete a book and everything under it. With `exclude`, its Calibre id joins the
 *  exclusion list so the next library sync doesn't bring it back. */
export async function deleteBook(
	id: string,
	{ exclude = false }: { exclude?: boolean } = {},
	fetchFn: typeof fetch = fetch
): Promise<void> {
	const res = await fetchFn(`/api/books/${id}?exclude=${exclude}`, { method: 'DELETE' });
	if (!res.ok) throw new Error(`DELETE /api/books/${id} → ${res.status}`);
}

/** URL of the raw EPUB stream for a book (served by GET /api/books/{id}/epub). */
export const epubUrl = (id: string): string => `/api/books/${id}/epub`;

// Mirrors RecipeIndexEntry from GET /api/books/{id}/recipe-index (snake_case): every recipe in
// the book (id · name · favourite state), used by the in-book reader to match headings to recipes.
export const recipeIndexEntrySchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	is_favourite: z.boolean()
});

export const recipeIndexResponseSchema = z.array(recipeIndexEntrySchema);

export type RecipeIndexEntry = z.infer<typeof recipeIndexEntrySchema>;

/** Fetch every recipe (id · name · favourite) for a book, in book order. */
export async function fetchRecipeIndex(
	bookId: string,
	fetchFn: typeof fetch = fetch
): Promise<RecipeIndexEntry[]> {
	const res = await fetchFn(`/api/books/${bookId}/recipe-index`);
	if (!res.ok) throw new Error(`GET /api/books/${bookId}/recipe-index → ${res.status}`);
	return recipeIndexResponseSchema.parse(await res.json());
}
