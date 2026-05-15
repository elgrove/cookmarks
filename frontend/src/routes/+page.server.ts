import type { PageServerLoad } from "./$types";
import { stats } from "$api";

export const load: PageServerLoad = async ({ fetch }) => {
  return { home: await stats.home({ fetch }) };
};
