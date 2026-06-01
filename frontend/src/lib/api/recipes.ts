import { z } from 'zod';

// The adjacent recipe in the current navigation context (prev/next).
export const recipeNeighbourSchema = z.object({
	id: z.string().uuid(),
	name: z.string()
});

// Mirrors the RecipeDetail wire shape from GET /api/recipes/{id} (snake_case).
export const recipeDetailSchema = z.object({
	id: z.string().uuid(),
	book_id: z.string().uuid(),
	book_title: z.string(),
	book_author: z.string(),
	book_has_cover: z.boolean(),
	name: z.string(),
	description: z.string().nullable(),
	ingredients: z.array(z.string()),
	instructions: z.array(z.string()),
	yields: z.string().nullable(),
	keywords: z.array(z.string()),
	has_image: z.boolean(),
	context: z.string(),
	previous: recipeNeighbourSchema.nullable(),
	next: recipeNeighbourSchema.nullable()
});

export type RecipeDetailResponse = z.infer<typeof recipeDetailSchema>;

/** Fetch and validate a single recipe's detail. `context` selects the prev/next
 *  ordering (defaults to book order). `fetchFn` is injectable for SSR/tests. */
export async function fetchRecipeDetail(
	id: string,
	fetchFn: typeof fetch = fetch,
	context = 'book'
): Promise<RecipeDetailResponse> {
	const res = await fetchFn(`/api/recipes/${id}?context=${encodeURIComponent(context)}`);
	if (!res.ok) throw new Error(`GET /api/recipes/${id} → ${res.status}`);
	return recipeDetailSchema.parse(await res.json());
}

// Mirrors the wire shapes from GET /api/recipes and GET /api/keywords (snake_case).
export const recipeSummarySchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	book_id: z.string().uuid(),
	book_title: z.string(),
	book_author: z.string(),
	keywords: z.array(z.string())
});

export const keywordSummarySchema = z.object({
	name: z.string(),
	recipe_count: z.number().int().nonnegative()
});

export const recipeSearchResultsSchema = z.object({
	total: z.number().int().nonnegative(),
	items: z.array(recipeSummarySchema),
	// Keywords most common among the matching recipes (selected ones excluded),
	// so the chips can re-rank to what narrows the search further.
	facets: z.array(keywordSummarySchema)
});

export const keywordsResponseSchema = z.array(keywordSummarySchema);

export type RecipeSummary = z.infer<typeof recipeSummarySchema>;
export type RecipeSearchResults = z.infer<typeof recipeSearchResultsSchema>;
export type KeywordSummary = z.infer<typeof keywordSummarySchema>;

export type SortKey = 'random' | 'name' | 'recent';

export type SearchCriteria = {
	q?: string;
	keywords?: string[];
	bookId?: string;
	author?: string;
	sort?: SortKey;
	// Stable shuffle seed for `sort: 'random'`, so pagination keeps one ordering.
	seed?: number;
	limit?: number;
	offset?: number;
};

/** True when the criteria ask for anything at all — the page is empty otherwise. */
export function hasCriteria(c: SearchCriteria): boolean {
	return Boolean(c.q?.trim() || c.keywords?.length || c.bookId || c.author);
}

function toParams(c: SearchCriteria): URLSearchParams {
	const p = new URLSearchParams();
	if (c.q?.trim()) p.set('q', c.q.trim());
	for (const kw of c.keywords ?? []) p.append('keyword', kw);
	if (c.bookId) p.set('book_id', c.bookId);
	if (c.author) p.set('author', c.author);
	if (c.sort) p.set('sort', c.sort);
	if (c.seed != null) p.set('seed', String(c.seed));
	if (c.limit != null) p.set('limit', String(c.limit));
	if (c.offset != null) p.set('offset', String(c.offset));
	return p;
}

/** Search recipes. `fetchFn` is injectable for SSR/tests. */
export async function searchRecipes(
	criteria: SearchCriteria,
	fetchFn: typeof fetch = fetch
): Promise<RecipeSearchResults> {
	const res = await fetchFn(`/api/recipes?${toParams(criteria)}`);
	if (!res.ok) throw new Error(`GET /api/recipes → ${res.status}`);
	return recipeSearchResultsSchema.parse(await res.json());
}

/** Fetch the keyword filter chips (name + how many recipes carry it). */
export async function fetchKeywords(fetchFn: typeof fetch = fetch): Promise<KeywordSummary[]> {
	const res = await fetchFn('/api/keywords');
	if (!res.ok) throw new Error(`GET /api/keywords → ${res.status}`);
	return keywordsResponseSchema.parse(await res.json());
}
