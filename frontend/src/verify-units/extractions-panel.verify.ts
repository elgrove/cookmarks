import ExtractionsPanel, {
	type ExtractionsPanelProps
} from '$lib/components/ExtractionsPanel.svelte';
import type { ExtractionRun } from '$lib/api/extraction';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ExtractionsPanelProps;

const base: ExtractionRun = {
	id: 'r1',
	book_id: 'b1',
	book_title: 'A Cookbook',
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

const run = (over: Partial<ExtractionRun> = {}): ExtractionRun => ({ ...base, ...over });

// Newest first, as the server returns them.
const runs: ExtractionRun[] = [
	run({ id: 'a', book_title: 'Salt Fat Acid Heat', status: 'done', recipes_found: 40 }),
	run({ id: 'b', book_title: 'The Food Lab', status: 'failed', recipes_found: 0, errors: ['boom'] }),
	run({ id: 'c', book_title: 'Plenty', status: 'review', recipes_found: 0, completed_at: null })
];

// The nested detail unit's status attribute — proves the report tracks the selection.
const detailStatus = (root: HTMLElement): string =>
	root
		.querySelector('[data-verify-unit="extraction-run-detail"]')
		?.getAttribute('data-verify-status') ?? '';

const unit: VerifiableUnit<Props> = {
	id: 'extractions-panel',
	title: 'Extractions panel',
	description:
		'The admin Extractions tab: every run newest-first with status at a glance, drilling into the selected run’s full report. Defaults to the newest run; clicking a row swaps the report.',
	kind: 'component',
	component: ExtractionsPanel,
	fixtures: [
		{
			id: 'populated',
			description: 'a history of runs, newest first, the newest selected by default',
			props: { runs }
		},
		{
			id: 'empty',
			description: 'no runs yet — the calm empty state',
			props: { runs: [] }
		},
		{
			id: 'single',
			description: 'a single run reads as "1 run" and is selected',
			props: { runs: [run({ id: 'solo', book_title: 'Just One', status: 'done' })] }
		},
		{
			id: 'select-second',
			description: 'clicking a row swaps the report to that run',
			props: { runs },
			act: ({ click }) => click('[data-run-id="b"]')
		},
		{
			id: 'many',
			description: 'probe: many runs with overlong titles and every status all render',
			probe: true,
			props: {
				runs: Array.from({ length: 12 }, (_, i) =>
					run({
						id: `x${i}`,
						book_title: `Très Long Cookbook Title — ${i} — 你好 ${'noodles '.repeat(4)}`,
						status: (['queued', 'running', 'review', 'done', 'failed'] as const)[i % 5],
						recipes_found: i * 3
					})
				)
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { runs }
		}
	],
	invariants: [
		{
			id: 'newest-first',
			description: 'every run renders as a row, in the given (newest-first) order',
			onlyFixtures: ['populated'],
			check: ({ contract, root, props }) => {
				const rows = root.querySelectorAll('.run-row');
				if (rows.length !== props.runs.length)
					return `expected ${props.runs.length} rows, saw ${rows.length}`;
				if (contract.count !== String(props.runs.length)) return `count=${contract.count}`;
				if (contract.first !== 'a') return `first=${contract.first}`;
				return contract.statuses === 'done,failed,review' || `statuses=${contract.statuses}`;
			}
		},
		{
			id: 'default-selects-newest',
			description: 'the newest run is selected by default and its report is shown',
			onlyFixtures: ['populated'],
			check: ({ contract, root }) => {
				if (contract.selected !== 'a') return `selected=${contract.selected}`;
				return detailStatus(root) === 'done' || `detail status=${detailStatus(root)}`;
			}
		},
		{
			id: 'click-selects',
			description: 'clicking the second row selects it and swaps the report to its status',
			onlyFixtures: ['select-second'],
			check: ({ contract, root }) => {
				if (contract.selected !== 'b') return `selected=${contract.selected}`;
				return detailStatus(root) === 'failed' || `detail status=${detailStatus(root)}`;
			}
		},
		{
			id: 'empty-state',
			description: 'no runs → empty flag set, no rows, the empty message shown',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.run-row')) return 'no rows expected';
				return (root.textContent ?? '').includes('No extraction runs yet') || 'empty message missing';
			}
		},
		{
			id: 'single-count',
			description: 'a single run reads as "1 run" (singular)',
			onlyFixtures: ['single'],
			check: ({ contract, root }) => {
				if (contract.count !== '1') return `count=${contract.count}`;
				return (root.textContent ?? '').includes('1 run') || 'singular count missing';
			}
		},
		{
			id: 'many-render',
			description: 'every run still renders as a row under the adversarial load',
			onlyFixtures: ['many'],
			check: ({ root, props }) => {
				const rows = root.querySelectorAll('.run-row');
				return rows.length === props.runs.length || `saw ${rows.length} rows`;
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
