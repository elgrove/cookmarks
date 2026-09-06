import BackfillProgress, {
	type BackfillProgressProps
} from '$lib/components/BackfillProgress.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = BackfillProgressProps;

const unit: VerifiableUnit<Props> = {
	id: 'enrichment-backfill-progress',
	title: 'Batch backfill progress',
	description:
		'The admin Batch backfill report: one phase (prepared / waiting / partial / complete / terminal / stale) with applied / failed / stale counts, chunk states and the snapshot-labelled cost estimate.',
	kind: 'component',
	component: BackfillProgress,
	fixtures: [
		{
			id: 'prepared',
			description: 'chunks prepared locally, nothing submitted yet',
			props: {
				status: 'queued',
				detail: { selected: 10, prepared: 10, submitted: 0, applied: 0 }
			}
		},
		{
			id: 'waiting',
			description: 'submitted and waiting on remote jobs, with a next poll',
			props: {
				status: 'waiting',
				detail: {
					selected: 10,
					prepared: 10,
					submitted: 10,
					succeeded: 0,
					applied: 0,
					next_poll_in_seconds: 60
				}
			}
		},
		{
			id: 'partial',
			description: 'partially applied while the rest is still in flight',
			props: {
				status: 'running',
				detail: {
					selected: 10,
					prepared: 10,
					submitted: 10,
					succeeded: 4,
					applied: 3,
					chunks_by_state: { submitted: 1, preparing: 1 },
					cost_estimate_usd: 0.42,
					pricing_snapshot_version: '2026-08-31'
				}
			}
		},
		{
			id: 'complete',
			description: 'every recipe applied, with the final cost estimate',
			props: {
				status: 'done',
				detail: {
					selected: 10,
					prepared: 10,
					submitted: 10,
					succeeded: 0,
					applied: 10,
					cost_estimate_usd: 1.2,
					pricing_snapshot_version: '2026-08-31'
				}
			}
		},
		{
			id: 'terminal',
			description: 'terminal partial failure: successes kept, failures explicit',
			props: {
				status: 'failed',
				detail: {
					selected: 10,
					prepared: 10,
					submitted: 10,
					applied: 7,
					terminal_failed: 2,
					stale: 1,
					last_provider_error: 'remote job state JOB_STATE_FAILED'
				}
			}
		},
		{
			id: 'stale',
			description: 'recipes changed mid-flight wait for a later run',
			props: {
				status: 'failed',
				detail: { selected: 10, prepared: 10, submitted: 10, applied: 8, stale: 2 }
			}
		},
		{
			id: 'empty',
			description: 'probe: a bare detail still renders a calm prepared state',
			probe: true,
			props: { status: 'queued', detail: {} }
		},
		{
			id: 'huge',
			description: 'probe: library-scale counts render in full',
			probe: true,
			props: {
				status: 'waiting',
				detail: {
					selected: 12000,
					prepared: 12000,
					submitted: 12000,
					applied: 3456,
					next_poll_in_seconds: 900
				}
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { status: 'queued', detail: {} }
		}
	],
	invariants: [
		{
			id: 'prepared-phase',
			description: 'nothing submitted reads as the prepared phase',
			onlyFixtures: ['prepared'],
			check: ({ contract }) =>
				(contract.phase === 'prepared' && contract.applied === '0') ||
				`phase=${contract.phase} applied=${contract.applied}`
		},
		{
			id: 'waiting-phase',
			description: 'submitted work with nothing applied reads as waiting',
			onlyFixtures: ['waiting'],
			check: ({ contract, root }) =>
				(contract.phase === 'waiting' &&
					contract.status === 'waiting' &&
					(root.textContent ?? '').includes('waiting on remote jobs')) ||
				`phase=${contract.phase} status=${contract.status}`
		},
		{
			id: 'partial-phase',
			description: 'partial application names the applied count and the cost snapshot',
			onlyFixtures: ['partial'],
			check: ({ contract, root }) =>
				(contract.phase === 'partial' &&
					contract.applied === '3' &&
					(root.textContent ?? '').includes('2026-08-31')) ||
				`phase=${contract.phase} applied=${contract.applied}`
		},
		{
			id: 'complete-phase',
			description: 'full coverage reads as complete with the honest total',
			onlyFixtures: ['complete'],
			check: ({ contract, root }) =>
				(contract.phase === 'complete' &&
					contract.applied === '10' &&
					(root.textContent ?? '').includes('Backfill complete')) ||
				`phase=${contract.phase} applied=${contract.applied}`
		},
		{
			id: 'terminal-phase',
			description: 'terminal failures surface the failed count, never a false complete',
			onlyFixtures: ['terminal'],
			check: ({ contract, root }) =>
				(contract.phase === 'terminal' &&
					contract.failed === '2' &&
					(root.textContent ?? '').includes('terminal failure')) ||
				`phase=${contract.phase} failed=${contract.failed}`
		},
		{
			id: 'stale-phase',
			description: 'mid-flight source changes read as stale with a resume pointer',
			onlyFixtures: ['stale'],
			check: ({ contract, root }) =>
				(contract.phase === 'stale' &&
					contract.stale === '2' &&
					(root.textContent ?? '').includes('later run')) ||
				`phase=${contract.phase} stale=${contract.stale}`
		},
		{
			id: 'empty-renders',
			description: 'a bare detail renders prepared without inventing counts',
			onlyFixtures: ['empty'],
			check: ({ contract }) =>
				(contract.phase === 'prepared' && contract.applied === '0') ||
				`phase=${contract.phase} applied=${contract.applied}`
		},
		{
			id: 'huge-renders',
			description: 'library-scale counts render in full on the waiting phase',
			onlyFixtures: ['huge'],
			check: ({ contract, root }) =>
				(contract.phase === 'partial' &&
					contract.applied === '3456' &&
					(root.textContent ?? '').includes('3456')) ||
				`phase=${contract.phase} applied=${contract.applied}`
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
