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

// Mirrors the ExtractionRunRead wire shape (snake_case). cost_usd is a string — a
// Decimal serialised by the backend, kept exact rather than coerced to a float;
// timestamps are ISO strings. pending_question is non-null only when status is review.
export const extractionRunSchema = z.object({
	id: z.string().uuid(),
	book_id: z.string().uuid(),
	status: z.enum(['queued', 'running', 'review', 'done', 'failed']),
	provider_name: z.string().nullable(),
	model_name: z.string().nullable(),
	extraction_method: z.enum(['file', 'block']).nullable(),
	total_chapters: z.number().int().nonnegative(),
	chapters_processed: z.number().int().nonnegative(),
	recipes_found: z.number().int().nonnegative(),
	cost_usd: z.string().nullable(),
	input_tokens: z.number().int().nonnegative().nullable(),
	output_tokens: z.number().int().nonnegative().nullable(),
	errors: z.array(z.string()),
	created_at: z.string(),
	started_at: z.string().nullable(),
	completed_at: z.string().nullable(),
	pending_question: reviewQuestionSchema.nullable()
});

export type ExtractionRun = z.infer<typeof extractionRunSchema>;

/** Queue recipe extraction for a book and return the freshly-created run. Fire-and-forget:
 *  the run executes in the background worker. `fetchFn` is injectable for SSR/tests. */
export async function triggerExtraction(
	bookId: string,
	fetchFn: typeof fetch = fetch
): Promise<ExtractionRun> {
	const res = await fetchFn(`/api/books/${bookId}/extract`, { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/books/${bookId}/extract → ${res.status}`);
	return extractionRunSchema.parse(await res.json());
}

/** The book's most recent extraction run, or null if it's never been extracted. The
 *  book page reads this on load so a run paused at REVIEW can surface its question. */
export async function fetchLatestRun(
	bookId: string,
	fetchFn: typeof fetch = fetch
): Promise<ExtractionRun | null> {
	const res = await fetchFn(`/api/books/${bookId}/extraction`);
	if (!res.ok) throw new Error(`GET /api/books/${bookId}/extraction → ${res.status}`);
	const data = await res.json();
	return data === null ? null : extractionRunSchema.parse(data);
}

/** Answer the review question on a paused run and resume it. Fire-and-forget: the
 *  graph runs to completion on the worker; the returned run is still REVIEW until then. */
export async function resumeExtraction(
	bookId: string,
	runId: string,
	answer: ReviewAnswer,
	fetchFn: typeof fetch = fetch
): Promise<ExtractionRun> {
	const res = await fetchFn(`/api/books/${bookId}/extract/${runId}/resume`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ response: answer })
	});
	if (!res.ok) throw new Error(`POST /api/books/${bookId}/extract/${runId}/resume → ${res.status}`);
	return extractionRunSchema.parse(await res.json());
}
