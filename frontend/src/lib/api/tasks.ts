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

/** Queue classification of every keyword that has not yet been examined. */
export async function triggerClassifyKeywords(fetchFn: typeof fetch = fetch): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/classify-keywords', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/tasks/classify-keywords → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Queue an AI-assisted merge of canonical ingredient variants. The worker repoints
 * recipe ingredient facts before removing duplicates; `queued` is the vocabulary size. */
export async function triggerDedupIngredients(fetchFn: typeof fetch = fetch): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/dedup-ingredients', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/tasks/dedup-ingredients → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}

/** Queue an import of new books from the Calibre library into the v2 DB. Existing
 *  books are left unchanged.
 *  Fire-and-forget: the import runs on the background worker and its result lands on
 *  the task run. `queued` is 0 (the book count isn't known until the worker reads the
 *  library). `fetchFn` is injectable for SSR/tests. */
export async function triggerCalibreSync(fetchFn: typeof fetch = fetch): Promise<TaskRunAck> {
	const res = await fetchFn('/api/tasks/calibre-sync', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/tasks/calibre-sync → ${res.status}`);
	return taskRunAckSchema.parse(await res.json());
}
