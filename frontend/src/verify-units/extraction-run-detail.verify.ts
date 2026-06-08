import ExtractionRunDetail, {
	type ExtractionRunDetailProps
} from '$lib/components/ExtractionRunDetail.svelte';
import type { ExtractionRun } from '$lib/api/extraction';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ExtractionRunDetailProps;

const base: ExtractionRun = {
	id: 'r1',
	book_id: 'b1',
	book_title: 'The Flavour Thesaurus',
	status: 'done',
	provider_name: 'GEMINI',
	model_name: 'gemini-2.5-flash',
	extraction_method: 'file',
	total_chapters: 12,
	chapters_processed: 12,
	recipes_found: 34,
	cost_usd: '0.0123',
	input_tokens: 45000,
	output_tokens: 6700,
	errors: [],
	created_at: '2026-06-05T10:00:00Z',
	started_at: '2026-06-05T10:00:01Z',
	completed_at: '2026-06-05T10:01:30Z',
	pending_question: null
};

// Spread (not `??`) so a fixture can deliberately set a nullable field back to null.
const run = (over: Partial<ExtractionRun> = {}): ExtractionRun => ({ ...base, ...over });

const unit: VerifiableUnit<Props> = {
	id: 'extraction-run-detail',
	title: 'Extraction run detail',
	description:
		'The per-run report: a hairline metadata table (method, provider, model, chapters, recipes, cost, tokens, timings) plus any errors, with a calm "no run selected" state when nothing is passed.',
	kind: 'component',
	component: ExtractionRunDetail,
	fixtures: [
		{
			id: 'done',
			description: 'a completed run — full report, no errors',
			props: { run: run() }
		},
		{
			id: 'failed',
			description: 'a failed run surfaces its errors',
			props: {
				run: run({
					id: 'r2',
					status: 'failed',
					recipes_found: 0,
					completed_at: '2026-06-05T10:00:20Z',
					errors: ['Chapter 3: model returned no JSON', 'Chapter 7: rate limited, gave up']
				})
			}
		},
		{
			id: 'review',
			description: 'a run paused at review shows the awaiting-review note',
			props: {
				run: run({
					id: 'r3',
					status: 'review',
					extraction_method: 'file',
					completed_at: null,
					recipes_found: 0,
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
			id: 'queued',
			description: 'a freshly-queued run — nothing measured yet, every blank reads as a dash',
			props: {
				run: run({
					id: 'r4',
					status: 'queued',
					extraction_method: null,
					model_name: null,
					total_chapters: 0,
					chapters_processed: 0,
					recipes_found: 0,
					cost_usd: null,
					input_tokens: null,
					output_tokens: null,
					started_at: null,
					completed_at: null
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
					chapters_processed: 4,
					recipes_found: 9,
					cost_usd: null,
					input_tokens: 1200,
					output_tokens: null,
					completed_at: null
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
			id: 'done-report',
			description: 'a done run renders with no errors',
			onlyFixtures: ['done'],
			check: ({ contract, root }) => {
				if (contract['has-run'] !== 'true') return `has-run=${contract['has-run']}`;
				if (contract.status !== 'done') return `status=${contract.status}`;
				if (contract['error-count'] !== '0') return `error-count=${contract['error-count']}`;
				return (root.textContent ?? '').includes(base.book_title) || 'book title missing';
			}
		},
		{
			id: 'failed-shows-errors',
			description: 'a failed run reports its errors, one row each',
			onlyFixtures: ['failed'],
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
			onlyFixtures: ['review'],
			check: ({ contract, root }) => {
				if (contract.status !== 'review') return `status=${contract.status}`;
				return (
					(root.textContent ?? '').includes('Awaiting review') || 'awaiting-review note missing'
				);
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
