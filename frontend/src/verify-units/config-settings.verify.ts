import ConfigSettings, {
	type ConfigSettingsConfig,
	type ConfigSettingsProps
} from '$lib/components/ConfigSettings.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ConfigSettingsProps;

const config = (over: Partial<ConfigSettingsConfig> = {}): ConfigSettingsConfig => ({
	isAdmin: true,
	userInstructions: null,
	rateLimit: 256,
	...over
});

const RATE = '#rate-limit';
const SAVE = '.save';
const INSTRUCTIONS = '#user-instructions';

const rateValue = (root: HTMLElement): string =>
	root.querySelector<HTMLInputElement>(RATE)?.value ?? '';

const unit: VerifiableUnit<Props> = {
	id: 'config-settings',
	title: 'Config settings',
	description:
		'The Settings form over user instructions, appearance, and (admin-only) the extraction rate limit. AI providers, models and task assignments live in the AI Configuration tab. Saving drives idle → saving → saved, or → error if the save rejects.',
	kind: 'component',
	component: ConfigSettings,
	fixtures: [
		{
			id: 'unset',
			description: 'a fresh config — default rate limit; the resting state',
			props: { config: config() }
		},
		{
			id: 'non-admin',
			description: 'non-admin user sees user instructions and appearance, while admin fields are hidden',
			props: {
				config: config({
					isAdmin: false,
					userInstructions: 'Vegetarian. Likes bold spices.'
				})
			}
		},
		{
			id: 'edit-instructions-save',
			description: 'updating user instructions and saving settles on the saved confirmation',
			props: {
				config: config({
					isAdmin: false,
					userInstructions: null
				}),
				onSaveUserInstructions: () => Promise.resolve()
			},
			act: async ({ type, click, wait }) => {
				type(INSTRUCTIONS, 'No dairy or peanuts.');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'instructions-over-limit',
			description: 'probe: instructions exceeding 4,000 characters mark over-limit and disable saving',
			probe: true,
			props: {
				config: config({
					isAdmin: false,
					userInstructions: null
				})
			},
			act: async ({ type, wait }) => {
				type(INSTRUCTIONS, 'a'.repeat(4001));
				await wait(0);
			}
		},
		{
			id: 'edit-save',
			description: 'changing the rate limit and saving settles on the saved confirmation',
			props: {
				config: config(),
				onSave: () => Promise.resolve()
			},
			act: async ({ type, click, wait }) => {
				type(RATE, '512');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'save-reject',
			description: 'probe: a rejected PATCH surfaces an error state, never a false "saved"',
			probe: true,
			props: {
				config: config(),
				onSave: () => Promise.reject(new Error('save failed'))
			},
			act: async ({ type, click, wait }) => {
				type(RATE, '512');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'huge-rate',
			description: 'probe: an absurd rate limit still renders one labelled numeric control',
			probe: true,
			props: { config: config({ rateLimit: 999999999 }) }
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { config: config() }
		}
	],
	invariants: [
		{
			id: 'unset-resting',
			description: 'default rate limit, not dirty, idle',
			onlyFixtures: ['unset'],
			check: ({ contract, root }) => {
				if (contract['rate-limit'] !== '256') return `rate=${contract['rate-limit']}`;
				if (contract.dirty !== 'false') return `dirty=${contract.dirty}`;
				if (rateValue(root) !== '256') return `input=${rateValue(root)}`;
				return contract.state === 'idle' || `state=${contract.state}`;
			}
		},
		{
			id: 'non-admin-hides-admin-fields',
			description: 'non-admin user hides the rate limit control',
			onlyFixtures: ['non-admin'],
			check: ({ contract, root }) => {
				if (contract['is-admin'] !== 'false') return `is-admin=${contract['is-admin']}`;
				if (root.querySelector('#user-instructions') === null) return 'missing user instructions textarea';
				return root.querySelector('#rate-limit') === null || 'rate limit visible for non-admin';
			}
		},
		{
			id: 'edit-instructions-settles',
			description: 'saving edited user instructions settles on the saved confirmation',
			onlyFixtures: ['edit-instructions-save'],
			check: ({ contract }) => contract.state === 'saved' || `state=${contract.state}`
		},
		{
			id: 'over-limit-disables-save',
			description: 'over-limit instructions report over-limit contract and disable save button',
			onlyFixtures: ['instructions-over-limit'],
			check: ({ contract, root }) => {
				if (contract['over-limit'] !== 'true') return `over-limit=${contract['over-limit']}`;
				const btn = root.querySelector<HTMLButtonElement>(SAVE);
				return (btn && btn.disabled) || 'save button not disabled when over limit';
			}
		},
		{
			id: 'edit-save-settles',
			description: 'a successful save lands on the saved state',
			onlyFixtures: ['edit-save'],
			check: ({ contract }) => contract.state === 'saved' || `state=${contract.state}`
		},
		{
			id: 'reject-errors',
			description: 'a rejected save lands on the error state (never a false saved)',
			onlyFixtures: ['save-reject'],
			check: ({ contract }) => contract.state === 'error' || `state=${contract.state}`
		},
		{
			id: 'huge-rate-rendered',
			description: 'the absurd rate limit is reflected in the numeric input',
			onlyFixtures: ['huge-rate'],
			check: ({ root }) => rateValue(root) === '999999999' || `rate=${rateValue(root)}`
		},
		{
			id: 'density-select-rendered',
			description: 'renders user-configurable book grid density select',
			onlyFixtures: ['unset'],
			check: ({ root, contract }) => {
				const select = root.querySelector<HTMLSelectElement>('#book-grid-density');
				if (!select) return 'missing #book-grid-density select';
				return contract['book-grid-density'] === 'standard' || `density=${contract['book-grid-density']}`;
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
