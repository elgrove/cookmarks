import { z } from 'zod';

// Mirrors the ExtractionRunRead wire shape from POST /api/books/{id}/extract
// (snake_case). cost_usd is a string — a Decimal serialised by the backend, kept
// exact rather than coerced to a float; timestamps are ISO strings.
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
	completed_at: z.string().nullable()
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
