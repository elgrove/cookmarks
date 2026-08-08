import { z } from 'zod';

export const statsSchema = z.object({
	books: z.number().int().nonnegative(),
	recipes: z.number().int().nonnegative(),
	keywords: z.number().int().nonnegative(),
	books_read: z.number().int().nonnegative()
});

export const bookFeatureSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	description: z.string(),
	recipe_count: z.number().int().nonnegative(),
	has_cover: z.boolean()
});

// A book part-way through, in the mode it was last read in: `fraction` is how far
// through, and `resume_recipe_id` is the recipe both modes pick back up at.
export const continueBookSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	mode: z.enum(['book', 'recipes']),
	fraction: z.number().min(0).max(1),
	resume_recipe_id: z.string().uuid().nullable(),
	has_cover: z.boolean()
});

// A recipe the reader opened recently — the trail back into whatever they were
// part-way through, at recipe rather than book granularity.
export const recentRecipeSchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	book_id: z.string().uuid(),
	book_title: z.string()
});

export const homeSchema = z.object({
	stats: statsSchema,
	book_of_the_day: bookFeatureSchema.nullable(),
	continue_reading: z.array(continueBookSchema),
	recently_read: z.array(recentRecipeSchema)
});

export type HomeResponse = z.infer<typeof homeSchema>;

/** Fetch and validate the home payload (stats + book of the day). */
export async function fetchHome(fetchFn: typeof fetch = fetch): Promise<HomeResponse> {
	const res = await fetchFn('/api/home');
	if (!res.ok) throw new Error(`GET /api/home → ${res.status}`);
	return homeSchema.parse(await res.json());
}
