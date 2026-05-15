import type { PageServerLoad } from "./$types";
import { books, keywords, lists, recipes } from "$api";

export const load: PageServerLoad = async ({ fetch, url }) => {
  const q = url.searchParams.get("q") ?? "";
  const book = url.searchParams.get("book") ?? undefined;
  const list = url.searchParams.get("list") ?? undefined;
  const selected_lists = url.searchParams.getAll("selected_lists");
  const selected_keywords = url.searchParams.getAll("selected_keywords");
  const vector_search = url.searchParams.get("vector_search") ?? "";
  const sort = url.searchParams.get("sort") ?? "";
  const group_logic = url.searchParams.get("group_logic") ?? "or";
  const page = Number(url.searchParams.get("page") ?? 1);

  const filter_field = url.searchParams.getAll("filter_field");
  const filter_op = url.searchParams.getAll("filter_op");
  const filter_value = url.searchParams.getAll("filter_value");
  const filter_group = url.searchParams.getAll("filter_group");
  const filter_logic = url.searchParams.getAll("filter_logic");

  const query: Record<string, string | number | boolean | string[] | undefined> = {
    q,
    book,
    list,
    selected_lists,
    selected_keywords,
    vector_search,
    sort,
    group_logic,
    page,
    filter_field,
    filter_op,
    filter_value,
    filter_group,
    filter_logic,
  };

  const [results, allLists, allKeywords, allAuthors] = await Promise.all([
    recipes.list(query, { fetch }),
    lists.list({ fetch }),
    keywords.list({ fetch }),
    books.authors({ fetch }),
  ]);

  return {
    results,
    allLists,
    allKeywords,
    allAuthors,
    state: {
      q,
      book,
      list,
      selected_lists,
      selected_keywords,
      vector_search,
      sort,
      group_logic,
      filters: filter_field.map((f, i) => ({
        field: f,
        op: filter_op[i] ?? "contains",
        value: filter_value[i] ?? "",
        group: Number(filter_group[i] ?? 0),
        logic: filter_logic[i] ?? "or",
      })),
    },
  };
};
