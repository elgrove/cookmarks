import { z } from 'zod';

// The adjacent recipe in the current navigation context (prev/next).
export const recipeNeighbourSchema = z.object({
	id: z.string().uuid(),
	name: z.string()
});

export const ingredientLineSchema = z.object({
	id: z.string().uuid(),
	position: z.number().int().nonnegative(),
	kind: z.enum(['ingredient', 'heading', 'note']).nullable(),
	text: z.string()
});

export const ingredientOccurrenceSchema = z.object({
	id: z.string().uuid(),
	line_id: z.string().uuid(),
	position: z.number().int().nonnegative(),
	ingredient_id: z.string().uuid(),
	ingredient_name: z.string(),
	quantity: z.string().nullable(),
	unit: z.string().nullable(),
	preparation: z.string().nullable(),
	optional: z.boolean(),
	alternative_group: z.number().int().nullable(),
	is_key: z.boolean(),
	parse_method: z.enum(['deterministic', 'ai']),
	resolution_method: z.enum(['canonical_name', 'alias', 'ai_existing', 'ai_created'])
});

export const recipeFactSchema = z.object({
	id: z.string(), name: z.string(), is_primary: z.boolean()
});

export const recipeCuisineSchema = z.object({
	id: z.string()
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
	ingredients_verbatim: z.array(ingredientLineSchema),
	ingredients: z.array(ingredientOccurrenceSchema),
	enrichment_status: z.enum(['pending', 'running', 'complete', 'failed']),
	cuisines: z.array(recipeCuisineSchema),
	methods: z.array(recipeFactSchema),
	courses: z.array(recipeFactSchema),
	instructions: z.array(z.string()),
	yields: z.string().nullable(),
	keywords: z.array(z.string()),
	has_image: z.boolean(),
	is_favourite: z.boolean(),
	context: z.string(),
	// What the reader last found when it looked for this recipe in the book's text:
	// null = never looked, true = found, false = the book doesn't name it anywhere.
	in_book: z.boolean().nullable(),
	previous: recipeNeighbourSchema.nullable(),
	next: recipeNeighbourSchema.nullable()
});

export type RecipeDetailResponse = z.infer<typeof recipeDetailSchema>;

/** Cache where the reader resolved a recipe in its book's EPUB — a CFI, or null when
 *  the scan found nothing (recorded all the same, as checked-and-absent). */
export async function reportEpubLocation(
	id: string,
	cfi: string | null,
	fetchFn: typeof fetch = fetch
): Promise<void> {
	const res = await fetchFn(`/api/recipes/${id}/epub-location`, {
		method: 'PUT',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ cfi })
	});
	if (!res.ok) throw new Error(`PUT /api/recipes/${id}/epub-location → ${res.status}`);
}

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

// Mirrors the RecipeViewState wire shape from POST /api/recipes/{id}/seen (snake_case).
export const recipeViewStateSchema = z.object({
	view_count: z.number().int().positive(),
	first_viewed_at: z.string(),
	last_viewed_at: z.string()
});

export type RecipeViewState = z.infer<typeof recipeViewStateSchema>;

/** Record that the reader has opened this recipe. Kept as a record of what has been
 *  looked at, not shown as read state; callers fire it and forget it. */
export async function markRecipeSeen(
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<RecipeViewState> {
	const res = await fetchFn(`/api/recipes/${id}/seen`, { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/recipes/${id}/seen → ${res.status}`);
	return recipeViewStateSchema.parse(await res.json());
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

// Mirrors SemanticSearchResults from GET /api/recipes/semantic (snake_case): a
// semantic result is a recipe summary plus its cosine distance from the query.
export const semanticResultSchema = recipeSummarySchema.extend({
	distance: z.number()
});

export const semanticSearchResultsSchema = z.object({
	// False when no embedding-capable AI provider is configured — the UI prompts to
	// set one up rather than reporting "no matches".
	available: z.boolean(),
	query: z.string(),
	total: z.number().int().nonnegative(),
	items: z.array(semanticResultSchema)
});

export type SemanticResult = z.infer<typeof semanticResultSchema>;
export type SemanticSearchResults = z.infer<typeof semanticSearchResultsSchema>;

export type SortKey = 'relevance' | 'random' | 'name' | 'recent' | 'book';

export type SearchCriteria = {
	q?: string;
	keywords?: string[];
	bookId?: string;
	author?: string;
	sort?: SortKey;
	// Stable shuffle seed for the shuffled sorts, so pagination keeps one ordering.
	// 'relevance' needs it too: it breaks score ties with the same shuffle.
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

/** The recipes-list URL filtered to a single keyword — the target of a clickable
 *  keyword chip anywhere in the app (result rows, recipe detail, book pages). */
export function keywordHref(name: string): string {
	return `/recipes?${criteriaToParams({ keywords: [name] })}`;
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
	if (sort === 'relevance' || sort === 'name' || sort === 'recent' || sort === 'random' || sort === 'book')
		c.sort = sort;
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

/** Semantic search: recipes ranked by meaning for a natural-language query. `limit`
 *  caps the result set; `fetchFn` is injectable for SSR/tests. */
export async function searchSemantic(
	q: string,
	limit = 30,
	fetchFn: typeof fetch = fetch
): Promise<SemanticSearchResults> {
	const params = new URLSearchParams({ q: q.trim(), limit: String(limit) });
	const res = await fetchFn(`/api/recipes/semantic?${params}`);
	if (!res.ok) throw new Error(`GET /api/recipes/semantic → ${res.status}`);
	return semanticSearchResultsSchema.parse(await res.json());
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
