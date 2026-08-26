import ExtractButton, { type ExtractButtonProps } from '$lib/components/ExtractButton.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ExtractButtonProps;

const BTN = '.extract';

const ariaLabel = (root: HTMLElement): string =>
	root.querySelector(BTN)?.getAttribute('aria-label') ?? '';

const unit: VerifiableUnit<Props> = {
	id: 'extract-button',
	title: 'Extract button',
	description:
		'The book-detail recipe-extraction trigger: a real button that labels Extract vs Re-extract by recipe count, and on click drives idle → posting → queued (fire-and-forget), or → error if the dispatch rejects.',
	kind: 'component',
	component: ExtractButton,
	fixtures: [
		{
			id: 'fresh',
			description: 'a book with no recipes — labelled "Extract recipes", idle',
			props: { recipeCount: 0 }
		},
		{
			id: 'extracted',
			description: 'a book that already has recipes — labelled "Re-extract recipes"',
			props: { recipeCount: 42 }
		},
		{
			id: 'click',
			description: 'clicking dispatches and settles to the queued confirmation',
			props: { recipeCount: 0, onExtract: () => Promise.resolve() },
			act: async ({ click, wait }) => {
				click(BTN);
				await wait(0);
			}
		},
		{
			id: 'reject',
			description: 'probe: a failed dispatch surfaces an error state, not a false "queued"',
			probe: true,
			props: { recipeCount: 0, onExtract: () => Promise.reject(new Error('broker down')) },
			act: async ({ click, wait }) => {
				click(BTN);
				await wait(0);
			}
		},
		{
			id: 'unavailable',
			description: 'a book with no EPUB: the control stays, disabled, and says why',
			props: { recipeCount: 0, unavailable: true }
		},
		{
			id: 'unavailable-click',
			description: 'probe: clicking the disabled control must not dispatch anything',
			probe: true,
			props: {
				recipeCount: 0,
				unavailable: true,
				onExtract: () => Promise.reject(new Error('must never be called'))
			},
			act: async ({ click, wait }) => {
				click(BTN);
				await wait(0);
			}
		},
		{
			id: 'huge-count',
			description: 'probe: an absurd recipe count still yields one labelled Re-extract control',
			probe: true,
			props: { recipeCount: 999999 }
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { recipeCount: 0 }
		}
	],
	invariants: [
		{
			id: 'fresh-idle',
			description: 'no recipes → idle state, recipe-count 0, "Extract recipes" label',
			onlyFixtures: ['fresh'],
			check: ({ contract, root }) => {
				if (contract.state !== 'idle') return `state=${contract.state}`;
				if (contract['recipe-count'] !== '0') return `recipe-count=${contract['recipe-count']}`;
				return ariaLabel(root) === 'Extract recipes' || `label=${ariaLabel(root)}`;
			}
		},
		{
			id: 'extracted-relabel',
			description: 'a book with recipes relabels to "Re-extract recipes"',
			onlyFixtures: ['extracted'],
			check: ({ contract, root }) => {
				if (contract['recipe-count'] !== '42') return `recipe-count=${contract['recipe-count']}`;
				return ariaLabel(root) === 'Re-extract recipes' || `label=${ariaLabel(root)}`;
			}
		},
		{
			id: 'click-queues',
			description: 'a successful dispatch lands on the queued state',
			onlyFixtures: ['click'],
			check: ({ contract }) => contract.state === 'queued' || `state=${contract.state}`
		},
		{
			id: 'reject-errors',
			description: 'a rejected dispatch lands on the error state (never a false queued)',
			onlyFixtures: ['reject'],
			check: ({ contract }) => contract.state === 'error' || `state=${contract.state}`
		},
		{
			id: 'unavailable-explains-itself',
			description: 'the disabled control names the reason, in its label and on the page',
			onlyFixtures: ['unavailable', 'unavailable-click'],
			check: ({ contract, root }) => {
				if (contract.state !== 'unavailable') return `state=${contract.state}`;
				const btn = root.querySelector<HTMLButtonElement>(BTN);
				if (!btn?.disabled) return 'the control is not disabled';
				if (!ariaLabel(root).includes('needs an EPUB')) return `label=${ariaLabel(root)}`;
				return (
					(btn.textContent ?? '').includes('needs an EPUB') ||
					`no visible reason: "${btn.textContent}"`
				);
			}
		},
		{
			id: 'huge-labelled',
			description: 'the control always carries a non-empty accessible label',
			onlyFixtures: ['huge-count'],
			check: ({ root }) => ariaLabel(root).length > 0 || 'extract control has no accessible label'
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
