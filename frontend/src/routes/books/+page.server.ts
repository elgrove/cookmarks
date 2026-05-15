import type { PageServerLoad } from "./$types";
import { books } from "$api";

export const load: PageServerLoad = async ({ fetch, url }) => {
  const search = url.searchParams.get("search") ?? "";
  const selected_authors = url.searchParams.getAll("selected_authors");
  const has_recipes = url.searchParams.get("has_recipes") === "1";
  const sort = url.searchParams.get("sort") ?? "random";
  const page = Number(url.searchParams.get("page") ?? 1);

  const [list, authors] = await Promise.all([
    books.list(
      { search, selected_authors, has_recipes, sort, page },
      { fetch },
    ),
    books.authors({ fetch }),
  ]);

  return { list, authors, filters: { search, selected_authors, has_recipes, sort } };
};
