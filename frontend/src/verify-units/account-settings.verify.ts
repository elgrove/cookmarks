import AccountSettings, {
	type AccountSettingsProps
} from '$lib/components/AccountSettings.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = AccountSettingsProps;

const NORMAL_INSTRUCTIONS =
	'Vegetarian. Gas hob, cast iron pan, no microwave. Dislikes cilantro.';
const MAX_INSTRUCTIONS = 'x'.repeat(4000);
const OVER_LIMIT_INSTRUCTIONS = 'x'.repeat(4001);

const TEXTAREA = '#cooking-instructions';
const SAVE = '.save-button';

const unit: VerifiableUnit<Props> = {
	id: 'account-settings',
	title: 'Account settings',
	description:
		'The personal account settings surface for editing cooking instructions. Saving drives idle → saving → saved, or → error if the PATCH rejects. Text over 4,000 characters disables save.',
	kind: 'component',
	component: AccountSettings,
	fixtures: [
		{
			id: 'normal',
			description: 'an existing profile with cooking instructions',
			props: { username: 'aaron', instructions: NORMAL_INSTRUCTIONS }
		},
		{
			id: 'empty',
			description: 'a fresh account with no instructions set',
			props: { username: 'sam', instructions: null }
		},
		{
			id: 'maximum-length',
			description: 'instructions at the exact 4,000 character limit',
			props: { username: 'aaron', instructions: MAX_INSTRUCTIONS }
		},
		{
			id: 'edit-save',
			description: 'editing instructions and saving settles on the saved confirmation',
			props: {
				username: 'aaron',
				instructions: NORMAL_INSTRUCTIONS,
				onSave: () => Promise.resolve()
			},
			act: async ({ type, click, wait }) => {
				type(TEXTAREA, 'Updated preferences. Vegan only.');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'save-error',
			description: 'probe: a rejected save surfaces an error message and state',
			probe: true,
			props: {
				username: 'aaron',
				instructions: NORMAL_INSTRUCTIONS,
				onSave: () => Promise.reject(new Error('Network disconnected'))
			},
			act: async ({ type, click, wait }) => {
				type(TEXTAREA, 'Updated preferences.');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'over-limit',
			description: 'probe: instructions exceeding 4,000 characters flags over-limit and disables saving',
			probe: true,
			props: {
				username: 'aaron',
				instructions: OVER_LIMIT_INSTRUCTIONS
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { username: 'aaron', instructions: NORMAL_INSTRUCTIONS }
		}
	],
	invariants: [
		{
			id: 'normal-resting',
			description: 'idle state, not dirty, matching length and content',
			onlyFixtures: ['normal'],
			check: ({ contract, root }) => {
				if (contract.state !== 'idle') return `state=${contract.state}`;
				if (contract.dirty !== 'false') return `dirty=${contract.dirty}`;
				if (contract['over-limit'] !== 'false') return `over-limit=${contract['over-limit']}`;
				const text = root.querySelector<HTMLTextAreaElement>(TEXTAREA)?.value;
				return text === NORMAL_INSTRUCTIONS || `text mismatch`;
			}
		},
		{
			id: 'empty-resting',
			description: 'idle state, zero length, empty textarea',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.state !== 'idle') return `state=${contract.state}`;
				if (contract.length !== '0') return `length=${contract.length}`;
				const text = root.querySelector<HTMLTextAreaElement>(TEXTAREA)?.value;
				return text === '' || `expected empty textarea`;
			}
		},
		{
			id: 'maximum-length-resting',
			description: 'length 4000 is accepted and not over limit',
			onlyFixtures: ['maximum-length'],
			check: ({ contract }) => {
				if (contract.length !== '4000') return `length=${contract.length}`;
				return contract['over-limit'] === 'false' || `over-limit=${contract['over-limit']}`;
			}
		},
		{
			id: 'edit-save-settles',
			description: 'successful save settles in saved state',
			onlyFixtures: ['edit-save'],
			check: ({ contract }) => contract.state === 'saved' || `state=${contract.state}`
		},
		{
			id: 'save-error-settles',
			description: 'rejected save settles in error state with message',
			onlyFixtures: ['save-error'],
			check: ({ contract, root }) => {
				if (contract.state !== 'error') return `state=${contract.state}`;
				const alert = root.querySelector('[role="alert"]');
				return alert?.textContent?.includes('Network disconnected') || 'missing error alert';
			}
		},
		{
			id: 'over-limit-flags-and-disables',
			description: 'over-limit is true and save button is disabled',
			onlyFixtures: ['over-limit'],
			check: ({ contract, root }) => {
				if (contract['over-limit'] !== 'true') return `over-limit=${contract['over-limit']}`;
				const btn = root.querySelector<HTMLButtonElement>(SAVE);
				return btn?.disabled === true || 'save button should be disabled';
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
