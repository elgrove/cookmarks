import TasksPanel, { type TasksPanelProps } from '$lib/components/TasksPanel.svelte';
import type { TaskRunAck } from '$lib/api/tasks';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = TasksPanelProps;

const RUN = '.run';
const CHECK = '.regen-check';
const DEDUP_RUN = '.dedup-run';
const ENRICHMENT_RUN = '.enrichment-run';
const BACKFILL_RUN = '.backfill-run';
const BACKFILL_RESUME = '.backfill-resume';
const PILOT_INPUT = '.pilot-input';
const REVIEWED_CHECK = '.reviewed-check';

// A handler that echoes the chosen mode back as the queued count, so an invariant can
// prove the regenerate flag actually reached the call (99 when regenerating, else 1).
const echoRun = ({ regenerate }: { regenerate: boolean }): Promise<TaskRunAck> =>
	Promise.resolve({ task: 'book_keywords', status: 'queued', queued: regenerate ? 99 : 1 });

const fixedRun =
	(queued: number) =>
	(): Promise<TaskRunAck> =>
		Promise.resolve({ task: 'book_keywords', status: 'queued', queued });

const fixedDedup =
	(queued: number) =>
	(): Promise<TaskRunAck> =>
		Promise.resolve({ task: 'keyword_dedup', status: 'queued', queued });

const fixedEnrichment =
	(queued: number) =>
	(): Promise<TaskRunAck> =>
		Promise.resolve({ task: 'recipe_enrichment_pilot', status: 'queued', queued });

const fixedBackfill =
	(queued: number) =>
	(opts: { pilotRunId: string; confirm: boolean }): Promise<TaskRunAck> =>
		Promise.resolve({ task: 'recipe_enrichment_backfill', status: 'queued', queued });

const unit: VerifiableUnit<Props> = {
	id: 'tasks-panel',
	title: 'Tasks panel',
	description:
		'The admin Tasks tab: on-demand "Generate book keywords" (with a regenerate-all toggle) and "Deduplicate keywords" triggers, each driving idle → running → queued (fire-and-forget), or → error if the dispatch rejects.',
	kind: 'component',
	component: TasksPanel,
	fixtures: [
		{
			id: 'idle',
			description: 'the panel at rest — nothing queued yet, regenerate off',
			props: { onRun: fixedRun(5) }
		},
		{
			id: 'run',
			description: 'running the task queues the eligible books and reports the count',
			props: { onRun: fixedRun(5) },
			act: async ({ click, wait }) => {
				click(RUN);
				await wait(0);
			}
		},
		{
			id: 'run-nothing',
			description: 'queuing nothing (all books already tagged) shows the calm up-to-date note',
			props: { onRun: fixedRun(0) },
			act: async ({ click, wait }) => {
				click(RUN);
				await wait(0);
			}
		},
		{
			id: 'regenerate',
			description: 'ticking "Regenerate all" passes the flag through to the run',
			props: { onRun: echoRun },
			act: async ({ click, wait }) => {
				click(CHECK);
				click(RUN);
				await wait(0);
			}
		},
		{
			id: 'reject',
			description: 'probe: a failed dispatch surfaces an error state, never a false "queued"',
			probe: true,
			props: { onRun: () => Promise.reject(new Error('broker down')) },
			act: async ({ click, wait }) => {
				click(RUN);
				await wait(0);
			}
		},
		{
			id: 'huge',
			description: 'probe: an absurd eligible count still renders one queued confirmation',
			probe: true,
			props: { onRun: fixedRun(999999) },
			act: async ({ click, wait }) => {
				click(RUN);
				await wait(0);
			}
		},
		{
			id: 'dedup-run',
			description: 'running the dedup queues the vocabulary and reports its size, book task untouched',
			props: { onRun: fixedRun(5), onDedup: fixedDedup(42) },
			act: async ({ click, wait }) => {
				click(DEDUP_RUN);
				await wait(0);
			}
		},
		{
			id: 'dedup-reject',
			description: 'probe: a failed dedup dispatch surfaces an error state, never a false "queued"',
			probe: true,
			props: { onRun: fixedRun(5), onDedup: () => Promise.reject(new Error('broker down')) },
			act: async ({ click, wait }) => {
				click(DEDUP_RUN);
				await wait(0);
			}
		},
		{
			id: 'enrichment-run',
			description: 'the live enrichment pilot queues its bounded sample for later review',
			props: { onRun: fixedRun(5), onEnrichmentPilot: fixedEnrichment(100) },
			act: async ({ click, wait }) => {
				click(ENRICHMENT_RUN);
				await wait(0);
			}
		},
		{
			id: 'enrichment-reject',
			description: 'probe: pilot dispatch failure is honestly visible',
			probe: true,
			props: {
				onRun: fixedRun(5),
				onEnrichmentPilot: () => Promise.reject(new Error('provider unavailable'))
			},
			act: async ({ click, wait }) => {
				click(ENRICHMENT_RUN);
				await wait(0);
			}
		},
		{
			id: 'backfill-run',
			description: 'a reviewed pilot ID launches the Batch backfill for the outstanding recipes',
			props: { onRun: fixedRun(5), onBackfill: fixedBackfill(248) },
			act: async ({ click, type, wait }) => {
				type(PILOT_INPUT, '3f1a2b3c-4d5e-4f6a-8b9c-0d1e2f3a4b5c');
				click(REVIEWED_CHECK);
				click(BACKFILL_RUN);
				await wait(0);
			}
		},
		{
			id: 'backfill-unreviewed',
			description: 'probe: without the review confirmation the launch still reports honestly',
			probe: true,
			props: {
				onRun: fixedRun(5),
				onBackfill: () => Promise.reject(new Error('confirm the pilot review'))
			},
			act: async ({ click, type, wait }) => {
				type(PILOT_INPUT, '3f1a2b3c-4d5e-4f6a-8b9c-0d1e2f3a4b5c');
				click(BACKFILL_RUN);
				await wait(0);
			}
		},
		{
			id: 'backfill-resume',
			description: 'resuming after a terminal run queues only the outstanding recipes',
			props: {
				onRun: fixedRun(5),
				onBackfillResume: () =>
					Promise.resolve({ task: 'recipe_enrichment_backfill', status: 'queued', queued: 3 })
			},
			act: async ({ click, wait }) => {
				click(BACKFILL_RESUME);
				await wait(0);
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { onRun: fixedRun(5) }
		}
	],
	invariants: [
		{
			id: 'idle-state',
			description: 'at rest: idle, regenerate off, nothing queued',
			onlyFixtures: ['idle'],
			check: ({ contract }) =>
				(contract.state === 'idle' &&
					contract.regenerate === 'false' &&
					contract.queued === '') ||
				`state=${contract.state} regenerate=${contract.regenerate} queued=${contract.queued}`
		},
		{
			id: 'dedup-idle',
			description: 'at rest the dedup task is idle too, with nothing queued',
			onlyFixtures: ['idle'],
			check: ({ contract }) =>
				(contract['dedup-state'] === 'idle' && contract['dedup-queued'] === '') ||
				`dedup-state=${contract['dedup-state']} dedup-queued=${contract['dedup-queued']}`
		},
		{
			id: 'run-queues',
			description: 'a successful run lands on done and reports the queued count',
			onlyFixtures: ['run'],
			check: ({ contract }) =>
				(contract.state === 'done' && contract.queued === '5') ||
				`state=${contract.state} queued=${contract.queued}`
		},
		{
			id: 'run-nothing-note',
			description: 'queuing zero books reaches done and shows the up-to-date message',
			onlyFixtures: ['run-nothing'],
			check: ({ contract, root }) => {
				if (contract.state !== 'done' || contract.queued !== '0')
					return `state=${contract.state} queued=${contract.queued}`;
				return (
					(root.textContent ?? '').includes('every extracted book already has keywords') ||
					'up-to-date note missing'
				);
			}
		},
		{
			id: 'regenerate-passed',
			description: 'the regenerate flag reaches the handler (queued echoes 99)',
			onlyFixtures: ['regenerate'],
			check: ({ contract }) =>
				(contract.state === 'done' &&
					contract.regenerate === 'true' &&
					contract.queued === '99') ||
				`state=${contract.state} regenerate=${contract.regenerate} queued=${contract.queued}`
		},
		{
			id: 'reject-errors',
			description: 'a rejected dispatch lands on the error state, with nothing queued',
			onlyFixtures: ['reject'],
			check: ({ contract }) =>
				(contract.state === 'error' && contract.queued === '') ||
				`state=${contract.state} queued=${contract.queued}`
		},
		{
			id: 'huge-rendered',
			description: 'the absurd count renders in full on the done confirmation',
			onlyFixtures: ['huge'],
			check: ({ contract, root }) => {
				if (contract.state !== 'done' || contract.queued !== '999999')
					return `state=${contract.state} queued=${contract.queued}`;
				return (root.textContent ?? '').includes('999999') || 'count not rendered in full';
			}
		},
		{
			id: 'dedup-queues',
			description: 'a successful dedup run lands on done and reports the vocabulary size',
			onlyFixtures: ['dedup-run'],
			check: ({ contract }) =>
				(contract['dedup-state'] === 'done' && contract['dedup-queued'] === '42') ||
				`dedup-state=${contract['dedup-state']} dedup-queued=${contract['dedup-queued']}`
		},
		{
			id: 'dedup-run-leaves-book-idle',
			description: 'running the dedup task does not disturb the book-keywords task',
			onlyFixtures: ['dedup-run'],
			check: ({ contract }) =>
				(contract.state === 'idle' && contract.queued === '') ||
				`book state=${contract.state} queued=${contract.queued}`
		},
		{
			id: 'dedup-reject-errors',
			description: 'a rejected dedup dispatch lands on the error state, with nothing queued',
			onlyFixtures: ['dedup-reject'],
			check: ({ contract }) =>
				(contract['dedup-state'] === 'error' && contract['dedup-queued'] === '') ||
				`dedup-state=${contract['dedup-state']} dedup-queued=${contract['dedup-queued']}`
		},
		{
			id: 'enrichment-queues',
			description: 'a successful pilot reports the reproducible sample count',
			onlyFixtures: ['enrichment-run'],
			check: ({ contract, root }) =>
				(contract['enrichment-state'] === 'done' &&
					contract['enrichment-queued'] === '100' &&
					(root.textContent ?? '').includes('Review the per-recipe results')) ||
				`state=${contract['enrichment-state']} queued=${contract['enrichment-queued']}`
		},
		{
			id: 'enrichment-reject-errors',
			description: 'a rejected pilot dispatch does not show a false queue confirmation',
			onlyFixtures: ['enrichment-reject'],
			check: ({ contract }) =>
				(contract['enrichment-state'] === 'error' && contract['enrichment-queued'] === '') ||
				`state=${contract['enrichment-state']} queued=${contract['enrichment-queued']}`
		},
		{
			id: 'backfill-queues',
			description: 'a reviewed pilot ID launches the backfill and reports the outstanding count',
			onlyFixtures: ['backfill-run'],
			check: ({ contract, root }) =>
				(contract['backfill-state'] === 'done' &&
					contract['backfill-queued'] === '248' &&
					contract['backfill-reviewed'] === 'true' &&
					(root.textContent ?? '').includes('Track prepared / waiting / applied')) ||
				`state=${contract['backfill-state']} queued=${contract['backfill-queued']}`
		},
		{
			id: 'backfill-unreviewed-errors',
			description: 'an unconfirmed launch surfaces the error state, never a false queue',
			onlyFixtures: ['backfill-unreviewed'],
			check: ({ contract }) =>
				(contract['backfill-state'] === 'error' && contract['backfill-queued'] === '') ||
				`state=${contract['backfill-state']} queued=${contract['backfill-queued']}`
		},
		{
			id: 'backfill-resume-queues',
			description: 'resuming queues the outstanding recipes without touching the launch form',
			onlyFixtures: ['backfill-resume'],
			check: ({ contract }) =>
				(contract['backfill-state'] === 'done' && contract['backfill-queued'] === '3') ||
				`state=${contract['backfill-state']} queued=${contract['backfill-queued']}`
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
