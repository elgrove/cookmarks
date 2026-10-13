import AdvancedRecipeSearch, {
	type AdvancedRecipeSearchProps
} from '$lib/components/AdvancedRecipeSearch.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { emptyFilters, type RecipeFilters } from '$lib/api/recipe-filters';

const filters: RecipeFilters = {
	version: 1,
	match: 'all',
	rules: [
		{ field: 'key_ingredient', operator: 'not_contains', value: 'chicken' },
		{ field: 'description', operator: 'is_empty', value: null }
	]
};
const unit: VerifiableUnit<AdvancedRecipeSearchProps> = {
	id: 'advanced-recipe-search',
	title: 'Advanced recipe search',
	kind: 'component',
	component: AdvancedRecipeSearch,
	fixtures: [
		{ id: 'closed', description: 'No modal when closed', props: { open: false } },
		{ id: 'existing', description: 'Opens with current rules', props: { open: true, filters } },
		{
			id: 'add-invalid',
			description: 'New rules need a value before Apply',
			props: { open: true },
			act: ({ click }) => click('.add')
		},
		{
			id: 'edit-valid',
			description: 'A completed text rule can apply',
			props: { open: true },
			act: ({ click, type }) => {
				click('.add');
				type('input', 'crème');
			}
		},
		{
			id: 'remove',
			description: 'Remove one rule',
			props: { open: true, filters },
			act: ({ click }) => click('.remove')
		},
		{
			id: 'clear',
			description: 'Clear only the draft',
			props: { open: true, filters },
			act: ({ click }) => click('.clear-rules')
		},
		{
			id: 'empty-any',
			description: 'An empty Match any draft is valid',
			props: { open: true, filters: { ...emptyFilters(), match: 'any' } }
		},
		{
			id: 'long-value',
			description: 'Probe: long Unicode text stays editable',
			probe: true,
			props: {
				open: true,
				filters: {
					version: 1,
					match: 'all',
					rules: [
						{ field: 'instructions', operator: 'contains', value: 'Crème brûlée 你好 '.repeat(20) }
					]
				}
			}
		},
		{
			id: 'lookup-failure',
			description: 'Probe: lookups fail without dropping current rules',
			probe: true,
			props: { open: true, filters, lookupError: 'Could not load lists.' }
		},
		{
			id: 'invalid-input',
			description: 'Probe: an incompatible field/operator cannot apply',
			probe: true,
			props: {
				open: true,
				filters: {
					version: 1,
					match: 'all',
					rules: [{ field: 'has_image', operator: 'contains', value: 'yes' }]
				}
			}
		},
		{
			id: 'contract-lie',
			description: 'Truthfulness sentinel',
			expectFail: true,
			props: { open: true }
		}
	],
	invariants: [
		{
			id: 'visibility',
			description: 'Dialog presence matches open state',
			check: ({ contract, root, props }) =>
				Boolean(root.querySelector('dialog')) === Boolean(props.open) &&
				contract.open === String(Boolean(props.open))
		},
		{
			id: 'rule-count',
			description: 'Draft contract agrees with rendered rule rows',
			check: ({ contract, root }) =>
				JSON.parse(contract.rules).length === root.querySelectorAll('.rule').length
		},
		{
			id: 'apply-validity',
			description: 'Apply enabled only for valid drafts',
			check: ({ contract, root }) => {
				const button = root.querySelector<HTMLButtonElement>('.apply');
				return !button || button.disabled === (contract.valid === 'false');
			}
		},
		{
			id: 'draft-edit',
			description: 'Typing completes the draft',
			onlyFixtures: ['edit-valid'],
			check: ({ contract }) =>
				contract.valid === 'true' && JSON.parse(contract.rules)[0].value === 'crème'
		},
		{
			id: 'remove-count',
			description: 'One rule remains after remove',
			onlyFixtures: ['remove'],
			check: ({ contract }) => JSON.parse(contract.rules).length === 1
		},
		{
			id: 'clear-draft',
			description: 'Clear does not mutate applied props',
			onlyFixtures: ['clear'],
			check: ({ contract, props }) =>
				JSON.parse(contract.rules).length === 0 && props.filters?.rules.length === 2
		},
		{
			id: 'invalid-message',
			description: 'An incomplete draft explains why',
			onlyFixtures: ['add-invalid', 'invalid-input'],
			check: ({ root }) => Boolean(root.querySelector('[role="alert"]')?.textContent)
		},
		{
			id: 'intentional-fail',
			description: 'Sentinel must fail',
			onlyFixtures: ['contract-lie'],
			check: () => 'Intentional truthfulness sentinel'
		}
	]
};
export default unit;
