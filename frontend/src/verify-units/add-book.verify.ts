import AddBook, { type AddBookProps } from '$lib/components/AddBook.svelte';
import type { StagedBook } from '$lib/api/ingest';
import type { TaskRun, TaskStatus } from '$lib/api/task-runs';
import type { ActContext, VerifiableUnit } from '$lib/verify/types';

type Props = AddBookProps;

const URL_FIELD = 'input[name="url"]';
const FETCH = '.url button';
const TITLE_FIELD = 'input[name="title"]';

const STAGED: StagedBook = {
	staging_id: 'staged-1',
	filename: 'The_Curry_Guy.epub',
	format: 'epub',
	title: 'The Curry Guy',
	author: 'Dan Toombs'
};

function run(id: string, status: TaskStatus, detail: Record<string, unknown>): TaskRun {
	return {
		id,
		task_type: 'book_ingest',
		status,
		book_id: null,
		book_title: null,
		provider_name: null,
		model_name: null,
		cost_usd: null,
		input_tokens: null,
		output_tokens: null,
		errors: status === 'failed' ? ['Already in the library: The Curry Guy'] : [],
		detail,
		created_at: '2026-08-15T20:00:00Z',
		started_at: null,
		completed_at: null,
		pending_question: null
	};
}

const INGESTED = { staging_id: 's', extract: false, title: 'The Curry Guy', author: 'Dan Toombs' };

/** Type a link and press Fetch — the one staging path `act` can drive, since a file
 *  input cannot be filled programmatically. */
const stageByUrl = async ({ type, click, wait }: ActContext) => {
	type(URL_FIELD, 'https://example.com/curry.epub');
	click(FETCH);
	await wait(0);
};

const unit: VerifiableUnit<Props> = {
	id: 'add-book',
	title: 'Add book',
	description:
		'The admin Add-book page: stage a cookbook by upload or download link, confirm the title and author read out of the file, and queue it. Recent ingest runs report below, and a run that failed as a duplicate offers to replace the copy already in the library.',
	kind: 'component',
	component: AddBook,
	fixtures: [
		{
			id: 'idle',
			description: 'nothing staged and nothing added yet — the resting intake state',
			props: { runs: [] }
		},
		{
			id: 'staged',
			description: 'a fetched book waiting for confirmation, title and author pre-filled',
			props: { runs: [], onStageUrl: () => Promise.resolve(STAGED) },
			act: stageByUrl
		},
		{
			id: 'staged-blank-title',
			description: 'clearing the title blocks the submit — a book with no name is not addable',
			props: { runs: [], onStageUrl: () => Promise.resolve(STAGED) },
			act: async (ctx) => {
				await stageByUrl(ctx);
				ctx.type(TITLE_FIELD, '');
			}
		},
		{
			id: 'runs-mixed',
			description: 'done, running and plainly-failed runs — none of them answerable by replacing',
			props: {
				runs: [
					run('r1', 'done', INGESTED),
					run('r2', 'running', { ...INGESTED, title: 'Persiana' }),
					run('r3', 'failed', { ...INGESTED, title: 'Sirocco' })
				]
			}
		},
		{
			id: 'duplicate-failed',
			description: 'a run refused as a duplicate offers to delete the existing copy and replace it',
			props: {
				runs: [
					run('r1', 'failed', { ...INGESTED, duplicate_of_book_id: 'book-1' }),
					run('r2', 'done', { ...INGESTED, title: 'Persiana' })
				]
			}
		},
		{
			id: 'hostile-metadata',
			description:
				'probe: a book whose title and filename are long and unicode-heavy still confirms cleanly',
			probe: true,
			props: {
				runs: [],
				onStageUrl: () =>
					Promise.resolve({
						staging_id: 'staged-2',
						filename: `${'Ω'.repeat(120)}.epub`,
						format: 'epub',
						title: `Крайне ${'长'.repeat(150)} 🍛`,
						author: `${'Ẅ'.repeat(90)}`
					})
			},
			act: stageByUrl
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { runs: [] }
		}
	],
	invariants: [
		{
			id: 'idle-rests-empty',
			description: 'nothing staged, nothing submittable, no runs',
			onlyFixtures: ['idle'],
			check: ({ contract }) => {
				if (contract.stage !== 'idle') return `stage=${contract.stage}`;
				if (contract['run-count'] !== '0') return `run-count=${contract['run-count']}`;
				return contract['can-submit'] === 'false' || 'an empty form offers a submit';
			}
		},
		{
			id: 'staging-prefills-and-enables',
			description: 'a staged book fills the form from the file and allows the submit',
			onlyFixtures: ['staged'],
			check: ({ contract, root }) => {
				if (contract.stage !== 'staged') return `stage=${contract.stage}`;
				if (contract['can-submit'] !== 'true') return 'a complete form refuses to submit';
				const title = root.querySelector<HTMLInputElement>(TITLE_FIELD)?.value;
				return title === STAGED.title || `title=${title}`;
			}
		},
		{
			id: 'blank-title-blocks-submit',
			description: 'an empty title disables the submit rather than queueing a nameless book',
			onlyFixtures: ['staged-blank-title'],
			check: ({ contract, root }) => {
				if (contract['can-submit'] !== 'false') return 'a blank title still offers a submit';
				const submit = root.querySelector<HTMLButtonElement>('button[type="submit"]');
				return submit?.disabled === true || 'the submit control is not actually disabled';
			}
		},
		{
			id: 'plain-failures-offer-no-replace',
			description: 'only a duplicate is answerable by replacing — a plain failure is not',
			onlyFixtures: ['runs-mixed'],
			check: ({ contract, root }) => {
				if (contract['run-count'] !== '3') return `run-count=${contract['run-count']}`;
				if (contract['duplicate-offers'] !== '0')
					return `duplicate-offers=${contract['duplicate-offers']}`;
				return (
					root.querySelector('[data-verify-duplicate-offer]') === null ||
					'a non-duplicate failure offers to replace something'
				);
			}
		},
		{
			id: 'duplicate-offers-replace',
			description: 'a duplicate-failed run carries the replace affordance, and only it does',
			onlyFixtures: ['duplicate-failed'],
			check: ({ contract, root }) => {
				if (contract['duplicate-offers'] !== '1')
					return `duplicate-offers=${contract['duplicate-offers']}`;
				const offers = root.querySelectorAll('[data-verify-duplicate-offer]');
				if (offers.length !== 1) return `${offers.length} replace affordances in the DOM`;
				const row = offers[0].closest('li');
				return row?.getAttribute('data-verify-run-status') === 'failed' || 'offered on a live run';
			}
		},
		{
			id: 'hostile-metadata-survives',
			description: 'an extreme title neither breaks the contract nor blocks the submit',
			onlyFixtures: ['hostile-metadata'],
			check: ({ contract }) => {
				if (contract.stage !== 'staged') return `stage=${contract.stage}`;
				if (contract['can-submit'] !== 'true') return 'a long but valid title blocks the submit';
				return contract.error === '' || `error=${contract.error}`;
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
