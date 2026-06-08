import TasksPanel, { type TasksPanelProps } from '$lib/components/TasksPanel.svelte';
import type { TaskRunAck } from '$lib/api/tasks';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = TasksPanelProps;

const RUN = '.run';
const CHECK = '.regen-check';
const DEDUP_RUN = '.dedup-run';

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
			id: 'intentional-fail',
			description: 'always fails — the truthfulness sentinel (expectFail)',
			onlyFixtures: ['contract-lie'],
			check: () => 'intentional failure: this sentinel must surface as FAIL'
		}
	]
};

export default unit;
