import type { PageServerLoad } from "./$types";
import { tasks } from "$api";

export const load: PageServerLoad = async ({ fetch }) => {
  return { overview: await tasks.overview({ fetch }) };
};
