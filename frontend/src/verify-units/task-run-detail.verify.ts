import TaskRunDetail, { type TaskRunDetailProps } from '$lib/components/TaskRunDetail.svelte';
import type { TaskRun } from '$lib/api/task-runs';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = TaskRunDetailProps;

// A completed extraction run — the richest type, with its metrics in `detail`.
const extractionBase: TaskRun = {
	id: 'r1',
	task_type: 'extraction',
	status: 'done',
	book_id: 'b1',
	book_title: 'The Flavour Thesaurus',
	provider_name: 'GEMINI',
	model_name: 'gemini-2.5-flash',
	cost_usd: '0.0123',
	input_tokens: 45000,
	output_tokens: 6700,
	errors: [],
	detail: {
		extraction_method: 'file',
		total_chapters: 12,
		chapters_processed: 12,
		recipes_found: 34,
		images_in_separate_chapters: false,
		images_can_be_matched: true
	},
	created_at: '2026-06-05T10:00:00Z',
	started_at: '2026-06-05T10:00:01Z',
	completed_at: '2026-06-05T10:01:30Z',
	pending_question: null
};

// Spread (not `??`) so a fixture can deliberately set a nullable field back to null.
const run = (over: Partial<TaskRun> = {}): TaskRun => ({ ...extractionBase, ...over });

// A non-extraction run: no book, AI cost/tokens absent, metrics in `detail`.
const maintenance = (over: Partial<TaskRun>): TaskRun => ({
	id: 'm1',
	task_type: 'book_keywords',
	status: 'done',
	book_id: null,
	book_title: null,
	provider_name: null,
	model_name: null,
	cost_usd: null,
	input_tokens: null,
	output_tokens: null,
	errors: [],
	detail: {},
	created_at: '2026-06-05T10:00:00Z',
	started_at: '2026-06-05T10:00:01Z',
	completed_at: '2026-06-05T10:00:09Z',
	pending_question: null,
	...over
});

const unit: VerifiableUnit<Props> = {
	id: 'task-run-detail',
	title: 'Task run detail',
	description:
		'The per-run report for any task type: a hairline metadata table whose rows adapt to the type (extraction shows method/chapters/recipes/cost; keywords/dedup/calibre show their own metrics), plus any errors, with a calm "no run selected" state.',
	kind: 'component',
	component: TaskRunDetail,
	fixtures: [
		{
			id: 'extraction-done',
			description: 'a completed extraction — full report against its book, no errors',
			props: { run: run() }
		},
		{
			id: 'extraction-failed',
			description: 'a failed extraction surfaces its errors',
			props: {
				run: run({
					id: 'r2',
					status: 'failed',
					completed_at: '2026-06-05T10:00:20Z',
					detail: { ...extractionBase.detail, recipes_found: 0 },
					errors: ['Chapter 3: model returned no JSON', 'Chapter 7: rate limited, gave up']
				})
			}
		},
		{
			id: 'extraction-review',
			description: 'an extraction paused at review shows the awaiting-review note',
			props: {
				run: run({
					id: 'r3',
					status: 'review',
					completed_at: null,
					detail: { ...extractionBase.detail, recipes_found: 0 },
					pending_question: {
						question: 'Zero images found. Does this cookbook have photos?',
						choices: [
							{ value: 'has_images', label: 'Yes, it has photos' },
							{ value: 'no_images', label: 'No photos' }
						]
					}
				})
			}
		},
		{
			id: 'book-keywords',
			description: 'a book-keyword tagging run reads its own metrics from detail',
			props: { run: maintenance({ detail: { books_tagged: 5, regenerate: false } }) }
		},
		{
			id: 'keyword-dedup',
			description:
				'a keyword-dedup run shows keywords analysed, the candidate window and the deterministic/AI split',
			props: {
				run: maintenance({
					id: 'm2',
					task_type: 'keyword_dedup',
					detail: {
						keywords_in: 40,
						candidates: 40,
						merges_applied: 6,
						pre_merges: 4,
						ai_merges: 2,
						ai_truncated: false,
						keywords_removed: 6,
						cursor_from: null,
						cursor_to: 'Wasabi'
					}
				})
			}
		},
		{
			id: 'keyword-dedup-truncated',
			description:
				'probe: the AI reply was cut off — the salvaged merges are reported and the truncation is named, not hidden behind a healthy-looking total',
			probe: true,
			props: {
				run: maintenance({
					id: 'm5',
					task_type: 'keyword_dedup',
					detail: {
						keywords_in: 5551,
						candidates: 1000,
						merges_applied: 1731,
						pre_merges: 1728,
						ai_merges: 3,
						ai_truncated: true,
						keywords_removed: 1731,
						cursor_from: 'Aubergine',
						cursor_to: 'Chorizo'
					}
				})
			}
		},
		{
			id: 'calibre-sync',
			description: 'a Calibre sync shows created / updated / orphaned / deleted / excluded counts',
			props: {
				run: maintenance({
					id: 'm3',
					task_type: 'calibre_sync',
					detail: {
						created: ['A Book', 'Another'],
						updated: ['A Third'],
						orphaned: [],
						deleted: ['A Removed Book'],
						excluded: ['A Book Kept Out']
					}
				})
			}
		},
		{
			id: 'calibre-failed',
			description: 'a Calibre sync against a missing library is a FAILED run carrying the error',
			props: {
				run: maintenance({
					id: 'm4',
					task_type: 'calibre_sync',
					status: 'failed',
					completed_at: '2026-06-05T10:00:02Z',
					detail: {},
					errors: ['Calibre database not found at /books/metadata.db']
				})
			}
		},
		{
			id: 'queued',
			description: 'a freshly-queued extraction — nothing measured yet, every blank reads as a dash',
			props: {
				run: run({
					id: 'r4',
					status: 'queued',
					model_name: null,
					cost_usd: null,
					input_tokens: null,
					output_tokens: null,
					started_at: null,
					completed_at: null,
					detail: {
						extraction_method: null,
						total_chapters: 0,
						chapters_processed: 0,
						recipes_found: 0,
						images_in_separate_chapters: null,
						images_can_be_matched: null
					}
				})
			}
		},
		{
			id: 'none',
			description: 'no run selected → the inert empty state',
			props: { run: null }
		},
		{
			id: 'messy',
			description:
				'probe: an overlong title, a wall of errors and absurd token counts all render without breaking',
			probe: true,
			props: {
				run: run({
					id: 'r5',
					status: 'failed',
					book_title: `Très Long Cookbook — 你好 ${'noodles '.repeat(12)}`,
					model_name: 'some/extremely-long-model-identifier-v3-preview-0925-experimental',
					input_tokens: 999999999,
					output_tokens: 123456789,
					errors: Array.from({ length: 8 }, (_, i) => `Error ${i}: ${'x'.repeat(80)}`)
				})
			}
		},
		{
			id: 'partial',
			description:
				'probe: started but never completed, with no cost — duration and cost both read as a dash',
			probe: true,
			props: {
				run: run({
					id: 'r6',
					status: 'running',
					cost_usd: null,
					input_tokens: 1200,
					output_tokens: null,
					completed_at: null,
					detail: { ...extractionBase.detail, chapters_processed: 4, recipes_found: 9 }
				})
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { run: run() }
		}
	],
	invariants: [
		{
			id: 'extraction-report',
			description: 'a done extraction renders against its book with no errors',
			onlyFixtures: ['extraction-done'],
			check: ({ contract, root }) => {
				if (contract['has-run'] !== 'true') return `has-run=${contract['has-run']}`;
				if (contract['task-type'] !== 'extraction') return `task-type=${contract['task-type']}`;
				if (contract.status !== 'done') return `status=${contract.status}`;
				if (contract['error-count'] !== '0') return `error-count=${contract['error-count']}`;
				const text = root.textContent ?? '';
				if (!text.includes(extractionBase.book_title!)) return 'book title missing';
				return text.includes('Recipes found') || 'recipes-found row missing';
			}
		},
		{
			id: 'failed-shows-errors',
			description: 'a failed run reports its errors, one row each',
			onlyFixtures: ['extraction-failed'],
			check: ({ contract, root }) => {
				if (contract.status !== 'failed') return `status=${contract.status}`;
				if (contract['error-count'] !== '2') return `error-count=${contract['error-count']}`;
				return (
					root.querySelectorAll('.error').length === 2 ||
					`saw ${root.querySelectorAll('.error').length} error rows`
				);
			}
		},
		{
			id: 'review-awaiting',
			description: 'a review run shows the awaiting-review note',
			onlyFixtures: ['extraction-review'],
			check: ({ contract, root }) => {
				if (contract.status !== 'review') return `status=${contract.status}`;
				return (
					(root.textContent ?? '').includes('Awaiting review') || 'awaiting-review note missing'
				);
			}
		},
		{
			id: 'book-keywords-rows',
			description: 'a book-keyword run reads as that type and shows its tagged count',
			onlyFixtures: ['book-keywords'],
			check: ({ contract, root }) => {
				if (contract['task-type'] !== 'book_keywords') return `task-type=${contract['task-type']}`;
				const text = root.textContent ?? '';
				if (!text.includes('Books tagged')) return 'books-tagged row missing';
				return text.includes('Book-keyword tagging') || 'title missing';
			}
		},
		{
			id: 'dedup-rows',
			description: 'a dedup run shows its merge metrics, split by stage',
			onlyFixtures: ['keyword-dedup', 'keyword-dedup-truncated'],
			check: ({ contract, root }) => {
				if (contract['task-type'] !== 'keyword_dedup') return `task-type=${contract['task-type']}`;
				const text = root.textContent ?? '';
				return (
					(text.includes('Merges applied') &&
						text.includes('Deterministic merges') &&
						text.includes('AI merges') &&
						text.includes('Candidates')) ||
					'dedup rows missing'
				);
			}
		},
		{
			id: 'dedup-split-within-window',
			description: 'the AI can never be credited with more merges than there were candidates',
			onlyFixtures: ['keyword-dedup', 'keyword-dedup-truncated'],
			check: ({ root }) => {
				const rows = [...root.querySelectorAll('.row')];
				const value = (label: string) =>
					Number(
						rows.find((r) => r.querySelector('dt')?.textContent === label)?.querySelector('dd')
							?.textContent ?? NaN
					);
				const ai = value('AI merges');
				const candidates = value('Candidates');
				if (Number.isNaN(ai) || Number.isNaN(candidates)) return 'split rows unreadable';
				return ai <= candidates || `${ai} AI merges over ${candidates} candidates`;
			}
		},
		{
			id: 'dedup-truncation-named',
			description: 'a salvaged run says so — a dead AI pass must not read as a healthy one',
			onlyFixtures: ['keyword-dedup-truncated'],
			check: ({ contract, root }) => {
				if (contract['ai-truncated'] !== 'true') return `ai-truncated=${contract['ai-truncated']}`;
				return (root.textContent ?? '').includes('Truncated') || 'truncation row missing';
			}
		},
		{
			id: 'calibre-rows',
			description: 'a Calibre sync shows created/updated/orphaned/deleted/excluded',
			onlyFixtures: ['calibre-sync'],
			check: ({ contract, root }) => {
				if (contract['task-type'] !== 'calibre_sync') return `task-type=${contract['task-type']}`;
				const text = root.textContent ?? '';
				return (
					(text.includes('Created') &&
						text.includes('Updated') &&
						text.includes('Orphaned') &&
						text.includes('Deleted') &&
						text.includes('Excluded')) ||
					'calibre rows missing'
				);
			}
		},
		{
			id: 'calibre-failure-recorded',
			description: 'a failed Calibre sync surfaces its error',
			onlyFixtures: ['calibre-failed'],
			check: ({ contract, root }) => {
				if (contract.status !== 'failed') return `status=${contract.status}`;
				if (contract['error-count'] !== '1') return `error-count=${contract['error-count']}`;
				return root.querySelectorAll('.error').length === 1 || 'error row missing';
			}
		},
		{
			id: 'none-empty',
			description: 'no run → empty state, no metadata table',
			onlyFixtures: ['none'],
			check: ({ contract, root }) => {
				if (contract['has-run'] !== 'false') return `has-run=${contract['has-run']}`;
				if (contract.status !== 'none') return `status=${contract.status}`;
				if (root.querySelector('.meta')) return 'metadata table should not render';
				return (root.textContent ?? '').includes('Select a run') || 'empty message missing';
			}
		},
		{
			id: 'messy-renders',
			description: 'every error in the wall renders despite the adversarial content',
			onlyFixtures: ['messy'],
			check: ({ contract, root }) => {
				if (contract['error-count'] !== '8') return `error-count=${contract['error-count']}`;
				return (
					root.querySelectorAll('.error').length === 8 ||
					`saw ${root.querySelectorAll('.error').length} error rows`
				);
			}
		},
		{
			id: 'intentional-fail',
			description: 'always fails — the truthfulness sentinel (expectFail)',
			onlyFixtures: ['contract-lie'],
			check: () => 'intentional failure: this sentinel must surface as FAIL'
		}
	]
};

export default unit;
