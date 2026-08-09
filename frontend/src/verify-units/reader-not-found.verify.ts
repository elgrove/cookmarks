import ReaderNotFound, { type ReaderNotFoundProps } from '$lib/components/ReaderNotFound.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ReaderNotFoundProps;

const base: Props = {
	recipeName: "Rosetta's Trofie with Basil Sauce",
	recipeHref: '/recipes/7c9e6679-7425-40de-944b-e07fc1f90ae7'
};

const unit: VerifiableUnit<Props> = {
	id: 'reader-not-found',
	title: 'Reader not-found state',
	description:
		'Shown when a targeted "open the book at this recipe" jump cannot find the recipe in the book\'s text: names the recipe, offers Open at the start, and links back to the recipe page. Purely presentational — the reader owns what "open at the start" does.',
	kind: 'component',
	component: ReaderNotFound,
	fixtures: [
		{
			id: 'default',
			description: 'an ordinary recipe name, with both ways out on offer',
			props: base
		},
		{
			id: 'open-at-start',
			description: 'clicking Open at the start echoes the action into the contract',
			props: base,
			act: ({ click }) => click('.start')
		},
		{
			id: 'long-name',
			description: 'probe: an overlong unicode recipe name must not break the layout',
			probe: true,
			props: {
				...base,
				recipeName:
					'Grand-mère’s Slow-Braised Bœuf Bourguignon with Crème Fraîche, Sauté Mushrooms & Far More Diacritics Than Will Ever Sit On One Line — Плов «по-домашнему»'
			}
		},
		{
			id: 'unknown-name',
			description: 'probe: an id absent from the book index has no name — the copy falls back',
			probe: true,
			props: { ...base, recipeName: null }
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: base
		}
	],
	invariants: [
		{
			id: 'name-in-copy',
			description: 'the contract carries the recipe name and, when known, the copy names it',
			check: ({ contract, root, props }) => {
				const want = props.recipeName ?? '';
				if (contract['recipe-name'] !== want)
					return `contract recipe-name=${contract['recipe-name']} expected ${want}`;
				const msg = root.querySelector('.msg')?.textContent ?? '';
				if (props.recipeName) return msg.includes(props.recipeName) || `copy does not name the recipe: "${msg}"`;
				return msg.includes('this recipe') || `no-name copy missing its fallback: "${msg}"`;
			}
		},
		{
			id: 'back-link',
			description: 'the way back is a real link to the recipe page, contract-matched',
			check: ({ contract, root, props }) => {
				if (contract['recipe-href'] !== props.recipeHref)
					return `contract recipe-href=${contract['recipe-href']} expected ${props.recipeHref}`;
				const a = root.querySelector(`a[href="${props.recipeHref}"]`);
				if (!a) return `no link back to ${props.recipeHref}`;
				return (a.textContent?.trim().length ?? 0) > 0 || 'back link has no accessible name';
			}
		},
		{
			id: 'start-action-labelled',
			description: 'the Open at the start control is a labelled button',
			check: ({ root }) => {
				const btn = root.querySelector('button.start');
				if (!btn) return 'no Open at the start button';
				return (btn.textContent?.trim().length ?? 0) > 0 || 'start button has no accessible name';
			}
		},
		{
			id: 'action-echo',
			description: 'the action contract is empty until Open at the start is clicked, then records it',
			check: ({ contract, fixture }) => {
				const want = fixture.id === 'open-at-start' ? 'open-at-start' : '';
				return contract.action === want || `action=${contract.action} expected "${want}"`;
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
