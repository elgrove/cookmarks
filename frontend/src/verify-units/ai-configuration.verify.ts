import AIConfiguration, {
	type AIConfigurationProps
} from '$lib/components/AIConfiguration.svelte';
import type {
	AiProvider,
	AiReadiness,
	Config,
	ModelRole
} from '$lib/api/config';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = AIConfigurationProps;

const PROVIDERS = (
	over: Partial<Record<AiProvider, { api_key_set?: boolean; model_ids?: string[] }>> = {}
): Config['providers'] => {
	const base: Record<AiProvider, { api_key_set: boolean; model_ids: string[] }> = {
		GEMINI: { api_key_set: false, model_ids: ['gemini-2.5-flash', 'gemini-2.5-flash-lite'] },
		ANTHROPIC: { api_key_set: false, model_ids: ['claude-sonnet-5', 'claude-haiku-4-5-20251001'] },
		OPENROUTER: {
			api_key_set: false,
			model_ids: [
				'google/gemini-2.5-flash',
				'google/gemini-2.5-flash-lite',
				'openai/gpt-oss-120b',
				'anthropic/claude-haiku-4.5'
			]
		}
	};
	const order: AiProvider[] = ['GEMINI', 'ANTHROPIC', 'OPENROUTER'];
	return order.map((provider, i) => ({
		provider,
		api_key_set: over[provider]?.api_key_set ?? base[provider].api_key_set,
		display_order: i,
		model_ids: over[provider]?.model_ids ?? base[provider].model_ids
	}));
};

const RECOMMENDATIONS: Config['recommendations'] = {
	GEMINI: {
		assistant: 'gemini-2.5-flash',
		ocr: 'gemini-2.5-flash',
		recipe_ingredients: 'gemini-2.5-flash-lite',
		recipe_semantics: 'gemini-2.5-flash'
	},
	ANTHROPIC: {
		assistant: 'claude-sonnet-5',
		recipe_ingredients: 'claude-haiku-4-5-20251001',
		recipe_semantics: 'claude-haiku-4-5-20251001'
	},
	OPENROUTER: {
		assistant: 'google/gemini-2.5-flash',
		recipe_ingredients: 'google/gemini-2.5-flash-lite',
		recipe_semantics: 'anthropic/claude-haiku-4.5'
	}
};

const assignment = (
	role: ModelRole,
	position: number,
	provider: AiProvider,
	model_id: string
): Config['task_assignments'][number] => ({ role, position, provider, model_id });

const config = (
	over: {
		providers?: Config['providers'];
		task_assignments?: Config['task_assignments'];
	} = {}
): Config => ({
	providers: over.providers ?? PROVIDERS(),
	task_assignments: over.task_assignments ?? [],
	recommendations: RECOMMENDATIONS,
	extraction_rate_limit_per_minute: 256
});

const NO_READINESS: AiReadiness = {
	extraction_available: false,
	assistant_available: false,
	ocr_available: false
};

const READY: AiReadiness = {
	extraction_available: true,
	assistant_available: true,
	ocr_available: true
};

const SAVE = '.ai-save';

const unit: VerifiableUnit<Props> = {
	id: 'ai-configuration',
	title: 'AI configuration',
	description:
		'The admin AI Configuration tab: ordered provider rows with write-only keys, per-provider model lists with free-text addition and guarded removal, task selectors grouped by product area with recommendation lines, the ordered ingredient fallback list, and visible extraction setup status. Saving drives idle → saving → saved, or → error if the save rejects.',
	kind: 'component',
	component: AIConfiguration,
	fixtures: [
		{
			id: 'setup-required',
			description: 'no keys anywhere — extraction setup is required; the resting state',
			props: { config: config(), readiness: NO_READINESS }
		},
		{
			id: 'gemini-ready',
			description: 'Gemini key stored — extraction, assistant and OCR all ready',
			props: {
				config: config({
					providers: PROVIDERS({ GEMINI: { api_key_set: true } })
				}),
				readiness: READY
			}
		},
		{
			id: 'custom-model',
			description: 'a free-text model added to Gemini — the model counts reflect it',
			props: {
				config: config({
					providers: PROVIDERS({
						GEMINI: {
							api_key_set: true,
							model_ids: ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-x']
						}
					})
				}),
				readiness: READY
			}
		},
		{
			id: 'explicit-assignment',
			description: 'the assistant explicitly assigned to Anthropic Sonnet',
			props: {
				config: config({
					providers: PROVIDERS({ ANTHROPIC: { api_key_set: true } }),
					task_assignments: [assignment('assistant', 0, 'ANTHROPIC', 'claude-sonnet-5')]
				}),
				readiness: {
					extraction_available: true,
					assistant_available: true,
					ocr_available: false
				}
			}
		},
		{
			id: 'ingredient-fallback',
			description: 'ingredient parsing with an ordered Gemini → Anthropic fallback list',
			props: {
				config: config({
					providers: PROVIDERS({
						GEMINI: { api_key_set: true },
						ANTHROPIC: { api_key_set: true }
					}),
					task_assignments: [
						assignment('recipe_ingredients', 0, 'GEMINI', 'gemini-2.5-flash-lite'),
						assignment('recipe_ingredients', 1, 'ANTHROPIC', 'claude-haiku-4-5-20251001')
					]
				}),
				readiness: READY
			}
		},
		{
			id: 'blocked-removal',
			description:
				'probe: a model referenced by a task cannot be removed — its control is disabled',
			probe: true,
			props: {
				config: config({
					providers: PROVIDERS({ GEMINI: { api_key_set: true } }),
					task_assignments: [
						assignment('recipe_ingredients', 0, 'GEMINI', 'gemini-2.5-flash-lite')
					]
				}),
				readiness: READY
			},
			act: async ({ click, wait }) => {
				click('.provider[data-provider="GEMINI"] .model-remove[data-model="gemini-2.5-flash-lite"]');
				await wait(0);
			}
		},
		{
			id: 'reorder',
			description: 'probe: moving a provider down reorders and marks the form dirty',
			probe: true,
			props: { config: config(), readiness: NO_READINESS },
			act: async ({ click, wait }) => {
				click('.provider[data-provider="GEMINI"] .order-down');
				await wait(0);
			}
		},
		{
			id: 'save-reject',
			description: 'probe: a rejected PATCH surfaces an error state, never a false "saved"',
			probe: true,
			props: {
				config: config(),
				readiness: NO_READINESS,
				onSave: () => Promise.reject(new Error('save failed'))
			},
			act: async ({ click, wait }) => {
				click('.provider[data-provider="GEMINI"] .order-down');
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'non-admin',
			description: 'non-admin users see no providers, models, keys or tasks',
			props: { config: config(), readiness: NO_READINESS, isAdmin: false }
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { config: config(), readiness: NO_READINESS }
		}
	],
	invariants: [
		{
			id: 'setup-required-resting',
			description: 'no keys: setup-required, catalogue order, not dirty, idle',
			onlyFixtures: ['setup-required'],
			check: ({ contract, root }) => {
				if (contract['setup-state'] !== 'setup-required') return `setup=${contract['setup-state']}`;
				if (contract['provider-order'] !== 'GEMINI,ANTHROPIC,OPENROUTER') {
					return `order=${contract['provider-order']}`;
				}
				if (contract.dirty !== 'false') return `dirty=${contract.dirty}`;
				if (root.querySelector('.provider') === null) return 'no provider rows rendered';
				return contract.state === 'idle' || `state=${contract.state}`;
			}
		},
		{
			id: 'ready-state',
			description: 'a stored key flips the setup state to ready',
			onlyFixtures: ['gemini-ready'],
			check: ({ contract }) =>
				contract['setup-state'] === 'ready' || `setup=${contract['setup-state']}`
		},
		{
			id: 'custom-model-counted',
			description: 'the added model is counted on its provider',
			onlyFixtures: ['custom-model'],
			check: ({ contract }) => {
				const counts = contract['model-counts'] ?? '';
				return counts.includes('GEMINI:3') || `counts=${counts}`;
			}
		},
		{
			id: 'explicit-assignment-surfaced',
			description: 'the pinned task assignment is explicit in the contract',
			onlyFixtures: ['explicit-assignment'],
			check: ({ contract }) => {
				const assignments = contract['task-assignments'] ?? '';
				return (
					assignments.includes('assistant=ANTHROPIC:claude-sonnet-5') ||
					`assignments=${assignments}`
				);
			}
		},
		{
			id: 'fallback-order-surfaced',
			description: 'the ordered fallback list reads primary-first in the contract',
			onlyFixtures: ['ingredient-fallback'],
			check: ({ contract }) => {
				if (contract['fallback-order'] !== 'GEMINI,ANTHROPIC') {
					return `fallback=${contract['fallback-order']}`;
				}
				const assignments = contract['task-assignments'] ?? '';
				return (
					assignments.includes(
						'recipe_ingredients=GEMINI:gemini-2.5-flash-lite+ANTHROPIC:claude-haiku-4-5-20251001'
					) || `assignments=${assignments}`
				);
			}
		},
		{
			id: 'removal-blocked',
			description: 'clicking remove on a referenced model leaves the list and dirty state untouched',
			onlyFixtures: ['blocked-removal'],
			check: ({ contract, root }) => {
				const btn = root.querySelector<HTMLButtonElement>(
					'.provider[data-provider="GEMINI"] .model-remove[data-model="gemini-2.5-flash-lite"]'
				);
				if (!btn) return 'remove control missing';
				if (!btn.disabled) return 'remove control enabled for a referenced model';
				const counts = contract['model-counts'] ?? '';
				if (!counts.includes('GEMINI:2')) return `counts=${counts}`;
				return contract.dirty === 'false' || `dirty=${contract.dirty}`;
			}
		},
		{
			id: 'reorder-marks-dirty',
			description: 'reordering providers updates the order contract and marks dirty',
			onlyFixtures: ['reorder'],
			check: ({ contract }) => {
				if (contract['provider-order'] !== 'ANTHROPIC,GEMINI,OPENROUTER') {
					return `order=${contract['provider-order']}`;
				}
				return contract.dirty === 'true' || `dirty=${contract.dirty}`;
			}
		},
		{
			id: 'reject-errors',
			description: 'a rejected save lands on the error state (never a false saved)',
			onlyFixtures: ['save-reject'],
			check: ({ contract }) => contract.state === 'error' || `state=${contract.state}`
		},
		{
			id: 'recommendations-shown',
			description: 'every task selector carries its recommendation line',
			onlyFixtures: ['gemini-ready'],
			check: ({ root }) => {
				const tasks = [...root.querySelectorAll('.task')];
				if (tasks.length === 0) return 'no tasks rendered';
				const missing = tasks.filter((t) => {
					const line = t.querySelector('.recommendation')?.textContent ?? '';
					return !line.startsWith('Recommended:');
				});
				return missing.length === 0 || `${missing.length} task(s) without a recommendation line`;
			}
		},
		{
			id: 'non-admin-sees-nothing',
			description: 'non-admin users receive no providers, models, keys or tasks',
			onlyFixtures: ['non-admin'],
			check: ({ contract, root }) => {
				if (contract['is-admin'] !== 'false') return `is-admin=${contract['is-admin']}`;
				if (root.querySelector('.provider') !== null) return 'provider controls visible';
				if (root.querySelector('.task') !== null) return 'task controls visible';
				if (root.querySelector('input[type="password"]') !== null) return 'key input visible';
				if (root.querySelector(SAVE) !== null) return 'save button visible';
				return (
					(root.textContent ?? '').includes('only available to administrators') ||
					'no access explanation rendered'
				);
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
