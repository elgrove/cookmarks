import TaskRunsPanel, { type TaskRunsPanelProps } from '$lib/components/TaskRunsPanel.svelte';
import type { TaskRun } from '$lib/api/task-runs';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = TaskRunsPanelProps;

const COMMON = {
	provider_name: null,
	model_name: null,
	cost_usd: null,
	input_tokens: null,
	output_tokens: null,
	errors: [] as string[],
	created_at: '2026-06-05T10:00:00Z',
	started_at: '2026-06-05T10:00:01Z',
	completed_at: '2026-06-05T10:00:30Z',
	pending_question: null
};

const extraction = (over: Partial<TaskRun> = {}): TaskRun => ({
	id: 'e1',
	task_type: 'extraction',
	status: 'done',
	book_id: 'b1',
	book_title: 'A Cookbook',
	...COMMON,
	provider_name: 'GEMINI',
	model_name: 'gemini-2.5-flash',
	cost_usd: '0.0123',
	input_tokens: 45000,
	output_tokens: 6700,
	detail: {
		extraction_method: 'file',
		total_chapters: 12,
		chapters_processed: 12,
		recipes_found: 34,
		images_in_separate_chapters: false,
		images_can_be_matched: true
	},
	...over
});

const maintenance = (over: Partial<TaskRun>): TaskRun => ({
	id: 'm1',
	task_type: 'book_keywords',
	status: 'done',
	book_id: null,
	book_title: null,
	...COMMON,
	detail: {},
	...over
});

// Newest first, mixed across task types — as the unified index returns them.
const runs: TaskRun[] = [
	extraction({ id: 'a', book_title: 'Salt Fat Acid Heat', detail: { recipes_found: 40 } }),
	maintenance({ id: 'b', task_type: 'book_keywords', detail: { books_tagged: 7, regenerate: false } }),
	maintenance({
		id: 'c',
		task_type: 'keyword_dedup',
		detail: { keywords_in: 30, merges_applied: 4, keywords_removed: 4 }
	}),
	extraction({ id: 'd', book_title: 'The Food Lab', status: 'failed', errors: ['boom'] }),
	maintenance({
		id: 'e',
		task_type: 'calibre_sync',
		status: 'failed',
		errors: ['no library'],
		detail: {}
	})
];

// The nested detail unit's status attribute — proves the report tracks the selection.
const detailStatus = (root: HTMLElement): string =>
	root
		.querySelector('[data-verify-unit="task-run-detail"]')
		?.getAttribute('data-verify-status') ?? '';

const unit: VerifiableUnit<Props> = {
	id: 'task-runs-panel',
	title: 'Task runs panel',
	description:
		'The admin Task Runs tab: every run across all task types, newest-first with status at a glance, filterable by type, drilling into the selected run’s full report. Defaults to the newest run; clicking a row swaps the report.',
	kind: 'component',
	component: TaskRunsPanel,
	fixtures: [
		{
			id: 'populated',
			description: 'a mixed history of runs, newest first, the newest selected by default',
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
			props: { runs: [extraction({ id: 'solo', book_title: 'Just One' })] }
		},
		{
			id: 'select-second',
			description: 'clicking a row swaps the report to that run',
			props: { runs },
			act: ({ click }) => click('[data-run-id="b"]')
		},
		{
			id: 'filter-extraction',
			description: 'the Extraction filter narrows the list to extraction runs only',
			props: { runs },
			act: ({ click }) => click('[data-filter="extraction"]')
		},
		{
			id: 'many',
			description: 'probe: many runs of every type and status with overlong titles all render',
			probe: true,
			props: {
				runs: Array.from({ length: 12 }, (_, i) =>
					i % 2 === 0
						? extraction({
								id: `x${i}`,
								book_title: `Très Long Cookbook — ${i} — 你好 ${'noodles '.repeat(4)}`,
								status: (['queued', 'running', 'review', 'done', 'failed'] as const)[i % 5],
								detail: { recipes_found: i * 3 }
							})
						: maintenance({
								id: `x${i}`,
								task_type: (['book_keywords', 'keyword_dedup', 'calibre_sync'] as const)[i % 3],
								status: (['queued', 'running', 'review', 'done', 'failed'] as const)[i % 5],
								detail: { books_tagged: i, merges_applied: i, created: [], updated: [] }
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
				return contract.statuses === 'done,done,done,failed,failed' || `statuses=${contract.statuses}`;
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
			description: 'clicking the second row selects it and swaps the report to its type',
			onlyFixtures: ['select-second'],
			check: ({ contract, root }) => {
				if (contract.selected !== 'b') return `selected=${contract.selected}`;
				const type = root
					.querySelector('[data-verify-unit="task-run-detail"]')
					?.getAttribute('data-verify-task-type');
				return type === 'book_keywords' || `detail task-type=${type}`;
			}
		},
		{
			id: 'filter-narrows',
			description: 'the Extraction filter shows only the two extraction runs, newest selected',
			onlyFixtures: ['filter-extraction'],
			check: ({ contract, root }) => {
				if (contract.filter !== 'extraction') return `filter=${contract.filter}`;
				if (contract.total !== '5') return `total=${contract.total}`;
				if (contract.count !== '2') return `count=${contract.count}`;
				const rows = root.querySelectorAll('.run-row');
				if (rows.length !== 2) return `saw ${rows.length} rows`;
				const allExtraction = Array.from(rows).every(
					(r) => r.getAttribute('data-task-type') === 'extraction'
				);
				if (!allExtraction) return 'non-extraction row leaked through the filter';
				return contract.selected === 'a' || `selected=${contract.selected}`;
			}
		},
		{
			id: 'empty-state',
			description: 'no runs → empty flag set, no rows, the empty message shown',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.run-row')) return 'no rows expected';
				return (root.textContent ?? '').includes('No task runs yet') || 'empty message missing';
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
