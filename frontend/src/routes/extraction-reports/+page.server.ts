import type { PageServerLoad } from "./$types";
import { extraction } from "$api";

export const load: PageServerLoad = async ({ fetch }) => {
  return { bundle: await extraction.reports({ fetch }) };
};
