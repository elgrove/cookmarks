import type { PageServerLoad } from "./$types";
import { lists } from "$api";

export const load: PageServerLoad = async ({ fetch, url }) => {
  const search = url.searchParams.get("search") ?? "";
  const all = await lists.list({ fetch });
  const filtered = search
    ? all.filter((l) => l.name.toLowerCase().includes(search.toLowerCase()))
    : all;
  return { lists: filtered, search };
};
