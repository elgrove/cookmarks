import type { PageServerLoad } from "./$types";
import { lists, recipes } from "$api";

export const load: PageServerLoad = async ({ fetch, params, url }) => {
  const ctx: Record<string, string | string[]> = {};
  for (const [k, v] of url.searchParams.entries()) {
    if (k in ctx) {
      const cur = ctx[k];
      ctx[k] = Array.isArray(cur) ? [...cur, v] : [cur as string, v];
    } else {
      ctx[k] = v;
    }
  }

  const [recipe, allLists] = await Promise.all([
    recipes.get(params.id, ctx as Record<string, string | string[]>, { fetch }),
    lists.list({ fetch }),
  ]);
  // Pass through the context string for "back" link
  return { recipe, allLists, contextQuery: url.searchParams.toString() };
};
