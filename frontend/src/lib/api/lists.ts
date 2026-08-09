import { z } from 'zod';
import { recipeSummarySchema } from './recipes';

// Mirrors the list wire shapes (snake_case) from the /api/lists endpoints.
export const listSummarySchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	is_default: z.boolean(),
	recipe_count: z.number().int().nonnegative()
});

export const listDetailSchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	is_default: z.boolean(),
	recipe_count: z.number().int().nonnegative(),
	recipes: z.array(recipeSummarySchema)
});

// A list paired with whether the current recipe is in it (add-to-list control).
export const listMembershipSchema = z.object({
	id: z.string().uuid(),
	name: z.string(),
	is_default: z.boolean(),
	contains: z.boolean()
});

const favouriteStateSchema = z.object({ is_favourite: z.boolean() });

// The outcome of a bulk membership operation: rows actually changed + new size.
export const bulkListResultSchema = z.object({
	changed: z.number().int().nonnegative(),
	recipe_count: z.number().int().nonnegative()
});

export const listsResponseSchema = z.array(listSummarySchema);
export const listMembershipsResponseSchema = z.array(listMembershipSchema);

export type ListSummary = z.infer<typeof listSummarySchema>;
export type ListDetail = z.infer<typeof listDetailSchema>;
export type ListMembership = z.infer<typeof listMembershipSchema>;
export type BulkListResult = z.infer<typeof bulkListResultSchema>;

/** The list endpoints a picker panel talks to — injectable so the harness can stub them. */
export type ListPanelApi = {
	fetchRecipeLists: (recipeId: string) => Promise<ListMembership[]>;
	addRecipeToList: (listId: string, recipeId: string) => Promise<void>;
	removeRecipeFromList: (listId: string, recipeId: string) => Promise<void>;
	createList: (name: string) => Promise<Pick<ListSummary, 'id' | 'name' | 'is_default'>>;
};

/** All lists, the default Favourites pinned first. `fetchFn` is injectable for tests. */
export async function fetchLists(fetchFn: typeof fetch = fetch): Promise<ListSummary[]> {
	const res = await fetchFn('/api/lists');
	if (!res.ok) throw new Error(`GET /api/lists → ${res.status}`);
	return listsResponseSchema.parse(await res.json());
}

/** Create a named list. Throws on a blank name (the server rejects it with 422). */
export async function createList(
	name: string,
	fetchFn: typeof fetch = fetch
): Promise<ListSummary> {
	const res = await fetchFn('/api/lists', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ name })
	});
	if (!res.ok) throw new Error(`POST /api/lists → ${res.status}`);
	return listSummarySchema.parse(await res.json());
}

/** A single list with its recipes as a text-first index. */
export async function fetchListDetail(
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<ListDetail> {
	const res = await fetchFn(`/api/lists/${id}`);
	if (!res.ok) throw new Error(`GET /api/lists/${id} → ${res.status}`);
	return listDetailSchema.parse(await res.json());
}

/** Rename a list. The default Favourites list is rejected by the server (409). */
export async function renameList(
	id: string,
	name: string,
	fetchFn: typeof fetch = fetch
): Promise<ListSummary> {
	const res = await fetchFn(`/api/lists/${id}`, {
		method: 'PATCH',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ name })
	});
	if (!res.ok) throw new Error(`PATCH /api/lists/${id} → ${res.status}`);
	return listSummarySchema.parse(await res.json());
}

/** Delete a list. The default Favourites list is rejected by the server (409). */
export async function deleteList(id: string, fetchFn: typeof fetch = fetch): Promise<void> {
	const res = await fetchFn(`/api/lists/${id}`, { method: 'DELETE' });
	if (!res.ok) throw new Error(`DELETE /api/lists/${id} → ${res.status}`);
}

/** Add a recipe to a list (idempotent server-side). */
export async function addRecipeToList(
	listId: string,
	recipeId: string,
	fetchFn: typeof fetch = fetch
): Promise<void> {
	const res = await fetchFn(`/api/lists/${listId}/recipes`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ recipe_id: recipeId })
	});
	if (!res.ok) throw new Error(`POST /api/lists/${listId}/recipes → ${res.status}`);
}

/** Remove a recipe from a list (idempotent server-side). */
export async function removeRecipeFromList(
	listId: string,
	recipeId: string,
	fetchFn: typeof fetch = fetch
): Promise<void> {
	const res = await fetchFn(`/api/lists/${listId}/recipes/${recipeId}`, { method: 'DELETE' });
	if (!res.ok) throw new Error(`DELETE /api/lists/${listId}/recipes/${recipeId} → ${res.status}`);
}

// The server caps a bulk payload at 500 ids; larger selections go in chunks.
const BULK_CHUNK = 500;

async function bulkOp(
	path: string,
	recipeIds: string[],
	fetchFn: typeof fetch
): Promise<BulkListResult> {
	let changed = 0;
	let recipe_count = 0;
	for (let i = 0; i < recipeIds.length; i += BULK_CHUNK) {
		const res = await fetchFn(path, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ recipe_ids: recipeIds.slice(i, i + BULK_CHUNK) })
		});
		if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
		const result = bulkListResultSchema.parse(await res.json());
		changed += result.changed;
		recipe_count = result.recipe_count;
	}
	return { changed, recipe_count };
}

/** Add many recipes to a list at once (idempotent server-side). */
export function bulkAddToList(
	listId: string,
	recipeIds: string[],
	fetchFn: typeof fetch = fetch
): Promise<BulkListResult> {
	return bulkOp(`/api/lists/${listId}/recipes/bulk`, recipeIds, fetchFn);
}

/** Remove many recipes from a list at once (idempotent server-side). */
export function bulkRemoveFromList(
	listId: string,
	recipeIds: string[],
	fetchFn: typeof fetch = fetch
): Promise<BulkListResult> {
	return bulkOp(`/api/lists/${listId}/recipes/bulk-remove`, recipeIds, fetchFn);
}

/** Which lists a recipe belongs to (Favourites first), for the add-to-list control. */
export async function fetchRecipeLists(
	recipeId: string,
	fetchFn: typeof fetch = fetch
): Promise<ListMembership[]> {
	const res = await fetchFn(`/api/recipes/${recipeId}/lists`);
	if (!res.ok) throw new Error(`GET /api/recipes/${recipeId}/lists → ${res.status}`);
	return listMembershipsResponseSchema.parse(await res.json());
}

/** Toggle a recipe's favourite star; resolves to the new favourite state. */
export async function toggleFavourite(
	recipeId: string,
	fetchFn: typeof fetch = fetch
): Promise<boolean> {
	const res = await fetchFn(`/api/recipes/${recipeId}/favourite`, { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/recipes/${recipeId}/favourite → ${res.status}`);
	return favouriteStateSchema.parse(await res.json()).is_favourite;
}
