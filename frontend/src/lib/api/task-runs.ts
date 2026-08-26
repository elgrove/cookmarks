import { z } from 'zod';

// One answer the operator can give to a paused run's review question: the resume
// token (`value`) and the operator-facing `label`.
export const reviewChoiceSchema = z.object({
	value: z.string(),
	label: z.string()
});

// The pending human-in-the-loop question on a run paused at REVIEW — what to ask and
// the choices to offer. Mirrors the backend ReviewQuestion.
export const reviewQuestionSchema = z.object({
	question: z.string(),
	choices: z.array(reviewChoiceSchema)
});

export type ReviewChoice = z.infer<typeof reviewChoiceSchema>;
export type ReviewQuestion = z.infer<typeof reviewQuestionSchema>;

// The two answers the graph accepts. Kept in lock-step with the backend review
// constants (pinned via contract/reviewquestion.example.json).
export type ReviewAnswer = 'has_images' | 'no_images';

export const taskTypeSchema = z.enum([
	'extraction',
	'book_keywords',
	'keyword_dedup',
	'calibre_sync',
	'book_ingest'
]);
export const taskStatusSchema = z.enum(['queued', 'running', 'review', 'done', 'failed']);

// Mirrors the TaskRunRead wire shape (snake_case) — one shape for every task type.
// `detail` carries each type's own metrics (see the *Detail interfaces below); cost_usd
// is a Decimal serialised as a string (kept exact); timestamps are ISO strings; book_*
// and pending_question are populated for extraction runs only.
export const taskRunSchema = z.object({
	id: z.string().uuid(),
	task_type: taskTypeSchema,
	status: taskStatusSchema,
	book_id: z.string().uuid().nullable(),
	book_title: z.string().nullable(),
	provider_name: z.string().nullable(),
	model_name: z.string().nullable(),
	cost_usd: z.string().nullable(),
	input_tokens: z.number().int().nonnegative().nullable(),
	output_tokens: z.number().int().nonnegative().nullable(),
	errors: z.array(z.string()),
	detail: z.record(z.string(), z.unknown()),
	created_at: z.string(),
	started_at: z.string().nullable(),
	completed_at: z.string().nullable(),
	pending_question: reviewQuestionSchema.nullable()
});

export type TaskRun = z.infer<typeof taskRunSchema>;
export type TaskType = z.infer<typeof taskTypeSchema>;
export type TaskStatus = z.infer<typeof taskStatusSchema>;

export const taskRunsSchema = z.array(taskRunSchema);

// The type-specific `detail` payloads, by task_type. The wire keeps `detail` a loose
// record; these describe what each type fills in, so the reporting UI can read it safely.
export interface ExtractionDetail {
	extraction_method: 'file' | 'block' | null;
	total_chapters: number;
	chapters_processed: number;
	recipes_found: number;
	images_in_separate_chapters: boolean | null;
	images_can_be_matched: boolean | null;
}
export interface BookKeywordsDetail {
	books_tagged: number;
	regenerate: boolean;
}
export interface KeywordDedupDetail {
	keywords_in: number;
	merges_applied: number;
	keywords_removed: number;
	// The rotating candidate window and the two merge stages counted apart. Optional:
	// older runs may omit them.
	candidates?: number;
	pre_merges?: number;
	ai_merges?: number;
	ai_truncated?: boolean;
	cursor_from?: string | null;
	cursor_to?: string | null;
}
export interface BookIngestDetail {
	// The job as submitted — kept on the run so the worker reads it from its own row,
	// and so a duplicate-failed run can be re-submitted as a replace without re-staging.
	staging_id: string;
	extract: boolean;
	title: string;
	author: string;
	format: string;
	converted: boolean;
	calibre_id: number;
	cover: boolean;
	replaced_calibre_id: number | null;
	extraction_queued: boolean;
	// Why extract-after-add did nothing, when it was asked for and did not happen.
	extraction_skipped?: string | null;
	// Set on a run that failed because the library already holds this book — the id of
	// the Cookmarks book it clashed with, which is what makes the replace offer possible.
	duplicate_of_book_id?: string;
}
export interface CalibreSyncDetail {
	created: string[];
	updated: string[];
	orphaned: string[];
	deleted: string[];
	excluded: string[];
}

/** Every task run, newest first — the unified admin reporting index. `type` filters to
 *  one task type (extraction / book_keywords / keyword_dedup / calibre_sync). */
export async function fetchTaskRuns(
	type?: TaskType,
	fetchFn: typeof fetch = fetch
): Promise<TaskRun[]> {
	const url = type ? `/api/task-runs?type=${type}` : '/api/task-runs';
	const res = await fetchFn(url);
	if (!res.ok) throw new Error(`GET ${url} → ${res.status}`);
	return taskRunsSchema.parse(await res.json());
}

/** Queue recipe extraction for a book and return the freshly-created run. Fire-and-forget:
 *  the run executes in the background worker. `fetchFn` is injectable for SSR/tests. */
export async function triggerExtraction(
	bookId: string,
	fetchFn: typeof fetch = fetch
): Promise<TaskRun> {
	const res = await fetchFn(`/api/books/${bookId}/extract`, { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/books/${bookId}/extract → ${res.status}`);
	return taskRunSchema.parse(await res.json());
}

/** The book's most recent extraction run, or null if it's never been extracted. The
 *  book page reads this on load so a run paused at REVIEW can surface its question. */
export async function fetchLatestRun(
	bookId: string,
	fetchFn: typeof fetch = fetch
): Promise<TaskRun | null> {
	const res = await fetchFn(`/api/books/${bookId}/extraction`);
	if (!res.ok) throw new Error(`GET /api/books/${bookId}/extraction → ${res.status}`);
	const data = await res.json();
	return data === null ? null : taskRunSchema.parse(data);
}

/** Answer the review question on a paused run and resume it. Fire-and-forget: the
 *  graph runs to completion on the worker; the returned run is still REVIEW until then. */
export async function resumeExtraction(
	bookId: string,
	runId: string,
	answer: ReviewAnswer,
	fetchFn: typeof fetch = fetch
): Promise<TaskRun> {
	const res = await fetchFn(`/api/books/${bookId}/extract/${runId}/resume`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ response: answer })
	});
	if (!res.ok)
		throw new Error(`POST /api/books/${bookId}/extract/${runId}/resume → ${res.status}`);
	return taskRunSchema.parse(await res.json());
}
