import ConfigSettings, {
	type ConfigSettingsConfig,
	type ConfigSettingsProps
} from '$lib/components/ConfigSettings.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ConfigSettingsProps;

const PROVIDERS: ConfigSettingsConfig['providers'] = [
	{ name: 'GEMINI', requiresApiKey: true },
	{ name: 'OPENROUTER', requiresApiKey: true },
	{ name: 'STUB', requiresApiKey: false }
];

const config = (over: Partial<ConfigSettingsConfig> = {}): ConfigSettingsConfig => ({
	aiProvider: null,
	apiKeySet: false,
	rateLimit: 256,
	providers: PROVIDERS,
	...over
});

const RATE = '#rate-limit';
const SAVE = '.save';

const rateValue = (root: HTMLElement): string =>
	root.querySelector<HTMLInputElement>(RATE)?.value ?? '';

const unit: VerifiableUnit<Props> = {
	id: 'config-settings',
	title: 'Config settings',
	description:
		'The admin Settings form over the Config singleton: AI provider, a write-only API key (set/not-set, replace, clear — never echoed), and the extraction rate limit. Saving drives idle → saving → saved, or → error if the PATCH rejects.',
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
			props: { config: config({ aiProvider: 'GEMINI', apiKeySet: true }) }
		},
		{
			id: 'stub-nokey',
			description: 'a keyless provider (Stub) hides the API-key field entirely',
			props: { config: config({ aiProvider: 'STUB' }) }
		},
		{
			id: 'edit-save',
			description: 'changing the rate limit and saving settles on the saved confirmation',
			props: {
				config: config({ aiProvider: 'GEMINI', apiKeySet: true }),
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
				config: config({ aiProvider: 'GEMINI', apiKeySet: true }),
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
			props: { config: config({ aiProvider: 'GEMINI', apiKeySet: true }) },
			act: async ({ click, wait }) => {
				click('.key-clear');
				await wait(0);
			}
		},
		{
			id: 'huge-rate',
			description: 'probe: an absurd rate limit still renders one labelled numeric control',
			probe: true,
			props: { config: config({ aiProvider: 'GEMINI', apiKeySet: true, rateLimit: 999999999 }) }
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { config: config({ aiProvider: 'GEMINI', apiKeySet: true }) }
		}
	],
	invariants: [
		{
			id: 'unset-resting',
			description: 'no provider, no key, not dirty, idle',
			onlyFixtures: ['unset'],
			check: ({ contract }) => {
				if (contract.provider !== 'none') return `provider=${contract.provider}`;
				if (contract['key-set'] !== 'false') return `key-set=${contract['key-set']}`;
				if (contract.dirty !== 'false') return `dirty=${contract.dirty}`;
				return contract.state === 'idle' || `state=${contract.state}`;
			}
		},
		{
			id: 'key-set-not-echoed',
			description: 'a stored key reads as set (keep action), and never appears as text',
			onlyFixtures: ['gemini-set'],
			check: ({ contract, root }) => {
				if (contract['key-set'] !== 'true') return `key-set=${contract['key-set']}`;
				if (contract['key-action'] !== 'keep') return `key-action=${contract['key-action']}`;
				// The password value is never rendered; only the masked "set" affordance shows.
				return root.querySelector('input[type="password"]') === null || 'key input exposed';
			}
		},
		{
			id: 'stub-hides-key',
			description: 'a keyless provider renders no API-key input',
			onlyFixtures: ['stub-nokey'],
			check: ({ contract, root }) => {
				if (contract['key-action'] !== 'na') return `key-action=${contract['key-action']}`;
				return root.querySelector('input[type="password"]') === null || 'key field shown for Stub';
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
				if (contract['key-action'] !== 'clear') return `key-action=${contract['key-action']}`;
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
