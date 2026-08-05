import { z } from 'zod';

export const statsSchema = z.object({
	books: z.number().int().nonnegative(),
	recipes: z.number().int().nonnegative(),
	keywords: z.number().int().nonnegative(),
	recipes_seen: z.number().int().nonnegative()
});

export const bookFeatureSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	description: z.string(),
	recipe_count: z.number().int().nonnegative(),
	has_cover: z.boolean()
});

// A book the reader is part-way through — the "continue reading" strip.
export const continueBookSchema = z.object({
	id: z.string().uuid(),
	title: z.string(),
	author: z.string(),
	recipe_count: z.number().int().nonnegative(),
	seen_count: z.number().int().nonnegative(),
	has_cover: z.boolean()
});

export const homeSchema = z.object({
	stats: statsSchema,
	book_of_the_day: bookFeatureSchema.nullable(),
	continue_reading: z.array(continueBookSchema)
});

export type HomeResponse = z.infer<typeof homeSchema>;

/** Fetch and validate the home payload (stats + book of the day). */
export async function fetchHome(fetchFn: typeof fetch = fetch): Promise<HomeResponse> {
	const res = await fetchFn('/api/home');
	if (!res.ok) throw new Error(`GET /api/home → ${res.status}`);
	return homeSchema.parse(await res.json());
}
