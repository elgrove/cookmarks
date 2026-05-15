import type { PageServerLoad } from "./$types";
import { config } from "$api";

export const load: PageServerLoad = async ({ fetch }) => {
  return { config: await config.get({ fetch }) };
};
