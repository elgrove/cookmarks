import { z } from 'zod';
import { taskRunSchema, type TaskRun } from './task-runs';

// Mirrors StagedBookRead from POST /api/ingest/stage/* (snake_case): a book file the
// server has accepted and inspected. Title and author are a starting point read out of
// the file (or its name) for the confirm form, not a finding.
export const stagedBookSchema = z.object({
	staging_id: z.string(),
	filename: z.string(),
	format: z.string(),
	title: z.string(),
	author: z.string()
});

export type StagedBook = z.infer<typeof stagedBookSchema>;

/** The confirmed ingest. `replace_book_id` names an existing book to stand down in
 *  favour of this file — its recipes, favourites and lists survive the swap. */
export interface IngestRequest {
	staging_id: string;
	title: string;
	author: string;
	extract: boolean;
	replace_book_id?: string | null;
}

// The endpoints answer a rejection with a sentence meant for the person who chose the
// file ("That book is over the 500 MB limit"), so surface it rather than a bare status.
async function failure(res: Response, what: string): Promise<Error> {
	let detail = '';
	try {
		const body = await res.json();
		detail = typeof body?.detail === 'string' ? body.detail : '';
	} catch {
		detail = '';
	}
	return new Error(detail || `${what} → ${res.status}`);
}

/** Upload a book file and get back what the server made of it. Nothing reaches the
 *  library until the ingest is confirmed. `fetchFn` is injectable for SSR/tests. */
export async function stageFile(file: File, fetchFn: typeof fetch = fetch): Promise<StagedBook> {
	const body = new FormData();
	body.append('file', file);
	const res = await fetchFn('/api/ingest/stage/file', { method: 'POST', body });
	if (!res.ok) throw await failure(res, 'POST /api/ingest/stage/file');
	return stagedBookSchema.parse(await res.json());
}

/** Same as an upload, for a direct download link — the server fetches it. */
export async function stageUrl(url: string, fetchFn: typeof fetch = fetch): Promise<StagedBook> {
	const res = await fetchFn('/api/ingest/stage/url', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ url })
	});
	if (!res.ok) throw await failure(res, 'POST /api/ingest/stage/url');
	return stagedBookSchema.parse(await res.json());
}

/** Queue the confirmed book for ingestion. Fire-and-forget: the work runs on the
 *  background worker and reports through the returned run. */
export async function submitIngest(
	request: IngestRequest,
	fetchFn: typeof fetch = fetch
): Promise<TaskRun> {
	const res = await fetchFn('/api/ingest', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(request)
	});
	if (!res.ok) throw await failure(res, 'POST /api/ingest');
	return taskRunSchema.parse(await res.json());
}
