import ConfigSettings, {
	type ConfigSettingsConfig,
	type ConfigSettingsProps
} from '$lib/components/ConfigSettings.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ConfigSettingsProps;

const PROVIDERS: NonNullable<ConfigSettingsConfig['providers']> = [
	{ name: 'ANTHROPIC', requiresApiKey: true },
	{ name: 'GEMINI', requiresApiKey: true },
	{ name: 'OPENROUTER', requiresApiKey: true }
];

const config = (over: Partial<ConfigSettingsConfig> = {}): ConfigSettingsConfig => ({
	isAdmin: true,
	userInstructions: null,
	extractionProvider: null,
	extractionApiKeySet: false,
	assistantProvider: null,
	assistantApiKeySet: false,
	rateLimit: 256,
	providers: PROVIDERS,
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
		'The Settings form over user instructions and AI configuration: user instructions for the assistant, theme preference, AI providers, write-only API keys (set/not-set, replace, clear — never echoed), and extraction rate limit. Non-admin users see only user instructions and appearance. Saving drives idle → saving → saved, or → error if the save rejects.',
	kind: 'component',
	component: ConfigSettings,
	fixtures: [
		{
			id: 'unset',
			description: 'a fresh config — no provider, no key, default rate limit; the resting state',
			props: { config: config() }
		},
		{
			id: 'gemini-set',
			description: 'provider Gemini with a key already stored — the key reads "set", not its value',
			props: { config: config({ extractionProvider: 'GEMINI', extractionApiKeySet: true }) }
		},
		{
			id: 'assistant-set',
			description: 'assistant Anthropic with a key already stored',
			props: { config: config({ assistantProvider: 'ANTHROPIC', assistantApiKeySet: true }) }
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
				config: config({ extractionProvider: 'GEMINI', extractionApiKeySet: true }),
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
				config: config({ extractionProvider: 'GEMINI', extractionApiKeySet: true }),
				onSave: () => Promise.reject(new Error('save failed'))
			},
			act: async ({ type, click, wait }) => {
				type(RATE, '512');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'clear-key',
			description: 'probe: clearing a stored key marks the form dirty with a pending clear',
			probe: true,
			props: { config: config({ extractionProvider: 'GEMINI', extractionApiKeySet: true }) },
			act: async ({ click, wait }) => {
				click('.extraction-key-clear');
				await wait(0);
			}
		},
		{
			id: 'huge-rate',
			description: 'probe: an absurd rate limit still renders one labelled numeric control',
			probe: true,
			props: {
				config: config({ extractionProvider: 'GEMINI', extractionApiKeySet: true, rateLimit: 999999999 })
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { config: config({ extractionProvider: 'GEMINI', extractionApiKeySet: true }) }
		}
	],
	invariants: [
		{
			id: 'unset-resting',
			description: 'no provider, no key, not dirty, idle',
			onlyFixtures: ['unset'],
			check: ({ contract }) => {
				if (contract['extraction-provider'] !== 'none') return `provider=${contract['extraction-provider']}`;
				if (contract['extraction-key-set'] !== 'false') return `key-set=${contract['extraction-key-set']}`;
				if (contract['assistant-provider'] !== 'none') return `assistant=${contract['assistant-provider']}`;
				if (contract.dirty !== 'false') return `dirty=${contract.dirty}`;
				return contract.state === 'idle' || `state=${contract.state}`;
			}
		},
		{
			id: 'non-admin-hides-admin-fields',
			description: 'non-admin user hides extraction and assistant admin controls',
			onlyFixtures: ['non-admin'],
			check: ({ contract, root }) => {
				if (contract['is-admin'] !== 'false') return `is-admin=${contract['is-admin']}`;
				if (root.querySelector('#user-instructions') === null) return 'missing user instructions textarea';
				if (root.querySelector('#extraction-provider') !== null) return 'extraction provider visible for non-admin';
				if (root.querySelector('#assistant-provider') !== null) return 'assistant provider visible for non-admin';
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
			id: 'key-set-not-echoed',
			description: 'a stored key reads as set (keep action), and never appears as text',
			onlyFixtures: ['gemini-set'],
			check: ({ contract, root }) => {
				if (contract['extraction-key-set'] !== 'true') return `key-set=${contract['extraction-key-set']}`;
				if (contract['extraction-key-action'] !== 'keep') return `key-action=${contract['extraction-key-action']}`;
				return root.querySelector('input[type="password"]') === null || 'key input exposed';
			}
		},
		{
			id: 'assistant-key-set',
			description: 'the assistant key reads as set and is not shown',
			onlyFixtures: ['assistant-set'],
			check: ({ contract, root }) => {
				if (contract['assistant-key-set'] !== 'true') return `key-set=${contract['assistant-key-set']}`;
				if (contract['assistant-key-action'] !== 'keep') return `key-action=${contract['assistant-key-action']}`;
				return root.querySelector('#assistant-api-key') === null || 'assistant key input exposed';
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
			id: 'clear-marks-dirty',
			description: 'clearing a stored key sets a pending clear and marks the form dirty',
			onlyFixtures: ['clear-key'],
			check: ({ contract }) => {
				if (contract['extraction-key-action'] !== 'clear') return `key-action=${contract['extraction-key-action']}`;
				return contract.dirty === 'true' || `dirty=${contract.dirty}`;
			}
		},
		{
			id: 'huge-rate-rendered',
			description: 'the absurd rate limit is reflected in the numeric input',
			onlyFixtures: ['huge-rate'],
			check: ({ root }) => rateValue(root) === '999999999' || `rate=${rateValue(root)}`
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

