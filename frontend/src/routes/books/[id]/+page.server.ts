import type { PageServerLoad } from "./$types";
import { books, recipes as recipesApi } from "$api";

export const load: PageServerLoad = async ({ fetch, params }) => {
  const book = await books.get(params.id, { fetch });
  const sample = await Promise.all(
    book.sample_recipe_ids.map((rid) => recipesApi.get(rid, {}, { fetch })),
  );
  return { book, sample };
};
