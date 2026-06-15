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
