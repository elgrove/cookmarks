import { z } from 'zod';

// Mirrors the TaskRunAck wire shape from POST /api/tasks/* (snake_case): which task was
// queued and how many units of work (books) it will process. Fire-and-forget — there's
// no live progress, mirroring extraction.
export const taskRunAckSchema = z.object({
	task: z.string(),
	status: z.string(),
	queued: z.number().int().nonnegative()
});

export type TaskRunAck = z.infer<typeof taskRunAckSchema>;

/** Queue AI generation of book-level keywords across the library. `regenerate` re-tags
 *  every extracted book; otherwise only those missing keywords. Fire-and-forget: the
 *  sweep runs on the background worker. `fetchFn` is injectable for SSR/tests. */
export async function triggerBookKeywords(
	regenerate = false,
	fetchFn: typeof fetch = fetch
): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/book-keywords', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ regenerate })
	});
	if (!res.ok) throw new Error(`POST /api/tasks/book-keywords → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Queue an AI-assisted dedup of the whole keyword vocabulary, merging near-duplicate
 *  tags ("Veggie" → "Vegetarian") across recipes and books. Fire-and-forget: the pass
 *  runs on the background worker. `queued` is the vocabulary size it will analyse.
 *  `fetchFn` is injectable for SSR/tests. */
export async function triggerDedupKeywords(fetchFn: typeof fetch = fetch): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/dedup-keywords', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/tasks/dedup-keywords → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Queue a sync of the Calibre library into the v2 DB, upserting books by calibre_id.
 *  Fire-and-forget: the sync runs on the background worker and its result lands on the
 *  task run. `queued` is 0 (the book count isn't known until the worker reads the
 *  library). `fetchFn` is injectable for SSR/tests. */
export async function triggerCalibreSync(fetchFn: typeof fetch = fetch): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/calibre-sync', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/tasks/calibre-sync → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Queue the bounded, reviewed live-API recipe enrichment pilot. It never uses Gemini
 * Batch: the response is only an acknowledgement; detailed outcomes land in Task Runs. */
export async function triggerRecipeEnrichmentPilot(
	fetchFn: typeof fetch = fetch
): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/recipe-enrichment-pilot', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/tasks/recipe-enrichment-pilot → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Launch the durable Gemini Batch backfill. Needs the done pilot run ID and an
 *  explicit confirmation its output was reviewed; the server rejects mismatched
 *  versions, other providers (422) and a second active backfill (409). */
export async function triggerRecipeEnrichmentBackfill(
	pilotRunId: string,
	confirmPilotReviewed: boolean,
	fetchFn: typeof fetch = fetch
): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/recipe-enrichment-backfill', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ pilot_run_id: pilotRunId, confirm_pilot_reviewed: confirmPilotReviewed })
	});
	if (!res.ok) throw new Error(`POST /api/tasks/recipe-enrichment-backfill → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Resume idempotently after a terminal run: a fresh parent run picks up only the
 *  recipes that are still outstanding. Safe to invoke repeatedly. */
export async function resumeRecipeEnrichmentBackfill(
	fetchFn: typeof fetch = fetch
): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/recipe-enrichment-backfill/resume', { method: 'POST' });
	if (!res.ok)
		throw new Error(`POST /api/tasks/recipe-enrichment-backfill/resume → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}
