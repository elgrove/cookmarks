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
	is_favourite: z.boolean(),
	context: z.string(),
	previous: recipeNeighbourSchema.nullable(),
	next: recipeNeighbourSchema.nullable()
});

export type RecipeDetailResponse = z.infer<typeof recipeDetailSchema>;

/** Fetch and validate a single recipe's detail. `contextParams` is the raw query
 *  string selecting the prev/next ordering (e.g. `context=book`, or
 *  `context=search&q=…&sort=…&seed=…`); empty defaults to book order on the
 *  backend. `fetchFn` is injectable for SSR/tests. */
export async function fetchRecipeDetail(
	id: string,
	fetchFn: typeof fetch = fetch,
	contextParams = ''
): Promise<RecipeDetailResponse> {
	const qs = contextParams ? `?${contextParams}` : '';
	const res = await fetchFn(`/api/recipes/${id}${qs}`);
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

// Mirrors GET /api/recipes/{id}/similar. `basis` records how the neighbours were
// found: 'vector' = nearest by embedding; 'keyword' = the shared-keyword fallback
// for recipes that carry no embedding.
export const similarRecipesSchema = z.object({
	basis: z.enum(['vector', 'keyword']),
	items: z.array(recipeSummarySchema)
});

export type RecipeSummary = z.infer<typeof recipeSummarySchema>;
export type RecipeSearchResults = z.infer<typeof recipeSearchResultsSchema>;
export type KeywordSummary = z.infer<typeof keywordSummarySchema>;
export type SimilarRecipesResponse = z.infer<typeof similarRecipesSchema>;

/** Fetch recipes similar to `id` — embedding nearest-neighbours, with a shared-keyword
 *  fallback server-side. Omit `limit` to take the server default (the full browse set);
 *  pass it for a small slice (e.g. the recipe-page footer's 5). `fetchFn` is injectable. */
export async function fetchSimilarRecipes(
	id: string,
	fetchFn: typeof fetch = fetch,
	limit?: number
): Promise<SimilarRecipesResponse> {
	const qs = limit != null ? `?limit=${limit}` : '';
	const res = await fetchFn(`/api/recipes/${id}/similar${qs}`);
	if (!res.ok) throw new Error(`GET /api/recipes/${id}/similar → ${res.status}`);
	return similarRecipesSchema.parse(await res.json());
}

export type SortKey = 'random' | 'name' | 'recent' | 'book';

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

export function criteriaToParams(c: SearchCriteria): URLSearchParams {
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

/** The query string that carries a search context into a recipe link, so the
 *  recipe's prev/next follow the search ordering (filters + sort + seed). Page
 *  size and offset are dropped — neighbours span the whole result set. */
export function searchContextQuery(c: SearchCriteria): string {
	const p = criteriaToParams(c);
	p.delete('limit');
	p.delete('offset');
	p.set('context', 'search');
	return p.toString();
}

/** Parse search criteria back out of URL query params — the inverse of
 *  `criteriaToParams`, so a search survives a round-trip through the URL. */
export function criteriaFromParams(p: URLSearchParams): SearchCriteria {
	const c: SearchCriteria = {};
	const q = p.get('q');
	if (q) c.q = q;
	const keywords = p.getAll('keyword');
	if (keywords.length) c.keywords = keywords;
	const bookId = p.get('book_id');
	if (bookId) c.bookId = bookId;
	const author = p.get('author');
	if (author) c.author = author;
	const sort = p.get('sort');
	if (sort === 'name' || sort === 'recent' || sort === 'random' || sort === 'book') c.sort = sort;
	const seed = p.get('seed');
	if (seed) c.seed = Number(seed);
	const offset = p.get('offset');
	if (offset) c.offset = Number(offset);
	return c;
}

/** Search recipes. `fetchFn` is injectable for SSR/tests. */
export async function searchRecipes(
	criteria: SearchCriteria,
	fetchFn: typeof fetch = fetch
): Promise<RecipeSearchResults> {
	const res = await fetchFn(`/api/recipes?${criteriaToParams(criteria)}`);
	if (!res.ok) throw new Error(`GET /api/recipes → ${res.status}`);
	return recipeSearchResultsSchema.parse(await res.json());
}

/** Fetch the most-used keyword filter chips (name + how many recipes carry it).
 *  `limit` caps the result server-side — the corpus has thousands and only the top
 *  few are ever rendered. `fetchFn` is injectable for SSR/tests. */
export async function fetchKeywords(
	limit = 50,
	fetchFn: typeof fetch = fetch
): Promise<KeywordSummary[]> {
	const res = await fetchFn(`/api/keywords?limit=${limit}`);
	if (!res.ok) throw new Error(`GET /api/keywords → ${res.status}`);
	return keywordsResponseSchema.parse(await res.json());
}
