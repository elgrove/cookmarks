import FavouriteToggle, {
	type FavouriteToggleProps
} from '$lib/components/FavouriteToggle.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = FavouriteToggleProps;

const FAV = '.fav';

const unit: VerifiableUnit<Props> = {
	id: 'favourite-toggle',
	title: 'Favourite toggle',
	description:
		'The recipe favourite star: a real button[aria-pressed] that reflects favourite state and fires a toggle handler when pressed.',
	kind: 'component',
	component: FavouriteToggle,
	fixtures: [
		{
			id: 'off',
			description: 'not a favourite — outline star, aria-pressed false',
			props: { isFavourite: false, recipeName: 'Dal Makhani' }
		},
		{
			id: 'on',
			description: 'a favourite — filled star, aria-pressed true',
			props: { isFavourite: true, recipeName: 'Dal Makhani' }
		},
		{
			id: 'click',
			description: 'clicking the star fires the toggle handler',
			props: { isFavourite: false, recipeName: 'Dal Makhani' },
			act: ({ click }) => click(FAV)
		},
		{
			id: 'long-name',
			description: 'probe: an overlong unicode name still yields a single labelled control',
			probe: true,
			props: {
				isFavourite: true,
				recipeName:
					'Slow-Roasted Pork Shoulder with Crème Fraîche, Pommes Purée & Sauce Gribiche — 你好'
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { isFavourite: true, recipeName: 'X' }
		}
	],
	invariants: [
		{
			id: 'off-state',
			description: 'the off state is aria-pressed false and reports favourite=false',
			onlyFixtures: ['off'],
			check: ({ contract, root }) => {
				if (contract.favourite !== 'false') return `favourite=${contract.favourite}`;
				const btn = root.querySelector(FAV);
				return btn?.getAttribute('aria-pressed') === 'false' || 'aria-pressed should be false';
			}
		},
		{
			id: 'on-state',
			description: 'the on state is aria-pressed true and reports favourite=true',
			onlyFixtures: ['on'],
			check: ({ contract, root }) => {
				if (contract.favourite !== 'true') return `favourite=${contract.favourite}`;
				const btn = root.querySelector(FAV);
				return btn?.getAttribute('aria-pressed') === 'true' || 'aria-pressed should be true';
			}
		},
		{
			id: 'click-fires',
			description: 'clicking records that the toggle handler ran',
			onlyFixtures: ['click'],
			check: ({ contract }) => contract.clicked === 'true' || `clicked=${contract.clicked}`
		},
		{
			id: 'labelled',
			description: 'the control always carries a non-empty accessible label',
			onlyFixtures: ['long-name'],
			check: ({ root }) => {
				const btn = root.querySelector(FAV);
				const label = btn?.getAttribute('aria-label') ?? '';
				return label.length > 0 || 'favourite control has no accessible label';
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
