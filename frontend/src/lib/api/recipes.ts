import { z } from 'zod';

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
	has_image: z.boolean()
});

export type RecipeDetailResponse = z.infer<typeof recipeDetailSchema>;

/** Fetch and validate a single recipe's detail. `fetchFn` is injectable for SSR/tests. */
export async function fetchRecipeDetail(
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<RecipeDetailResponse> {
	const res = await fetchFn(`/api/recipes/${id}`);
	if (!res.ok) throw new Error(`GET /api/recipes/${id} → ${res.status}`);
	return recipeDetailSchema.parse(await res.json());
}
