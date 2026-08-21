import ListPicker, { type ListPickerProps } from '$lib/components/ListPicker.svelte';
import type { ListMembership } from '$lib/api/lists';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ListPickerProps;

function membership(over: Partial<ListMembership> = {}): ListMembership {
	return {
		id: over.id ?? 'l1',
		name: over.name ?? 'A list',
		is_default: over.is_default ?? false,
		contains: over.contains ?? false
	};
}

const lists: ListMembership[] = [
	membership({ id: 'fav', name: 'Favourites', is_default: true, contains: true }),
	membership({ id: 'wk', name: 'Weeknight dinners', contains: false }),
	membership({ id: 'tt', name: 'To try', contains: true })
];

const TRIGGER = '.trigger';
const TOGGLE = '.list-toggle';
const SECOND_ROW = '.lists li:nth-child(2) .list-toggle';
const CREATE_INPUT = '.create-input';
const CREATE_BTN = '.create-btn';

const unit: VerifiableUnit<Props> = {
	id: 'add-to-list',
	title: 'Add-to-list control',
	description:
		'A disclosure that lists every list with its membership as a button[aria-pressed], plus an inline create-new field, dismissed as soon as a choice is made. Favourites is pinned first.',
	kind: 'component',
	component: ListPicker,
	fixtures: [
		{
			id: 'closed',
			description: 'the resting trigger with the panel collapsed',
			props: { lists, open: false }
		},
		{
			id: 'open',
			description: 'the open panel: every list with its membership pressed state',
			props: { lists, open: true }
		},
		{
			id: 'open-via-click',
			description: 'clicking the trigger opens the panel',
			props: { lists, open: false },
			act: ({ click }) => click(TRIGGER)
		},
		{
			id: 'toggle-member',
			description: 'clicking an unticked list row adds it and dismisses the panel',
			props: { lists, open: true },
			act: async ({ click, wait }) => {
				click(SECOND_ROW);
				await wait(0);
			}
		},
		{
			id: 'toggle-error',
			description: 'a rejected toggle leaves the panel open so the row can be retried',
			props: {
				lists,
				open: true,
				onToggle: () => Promise.reject(new Error('stub: could not add'))
			},
			act: async ({ click, wait }) => {
				click(SECOND_ROW);
				await wait(0);
			}
		},
		{
			id: 'create',
			description: 'typing a name and pressing Create fires the create handler, then dismisses',
			props: { lists, open: true },
			act: async ({ type, click, wait }) => {
				type(CREATE_INPUT, 'Brunch');
				click(CREATE_BTN);
				await wait(0);
			}
		},
		{
			id: 'long-names',
			description: 'probe: many lists with overlong unicode names all render and stay labelled',
			probe: true,
			props: {
				open: true,
				lists: Array.from({ length: 8 }, (_, i) =>
					membership({
						id: `x${i}`,
						name: `Très Long Collection Name Number ${i} — 你好 ${'spaghetti '.repeat(3)}`,
						is_default: i === 0,
						contains: i % 2 === 0
					})
				)
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { lists, open: true }
		}
	],
	invariants: [
		{
			id: 'closed-hides-panel',
			description: 'the collapsed state renders the trigger but no panel',
			onlyFixtures: ['closed'],
			check: ({ contract, root }) => {
				if (contract.open !== 'false') return `open=${contract.open}`;
				if (root.querySelector('.panel')) return 'panel should not render while closed';
				return root.querySelector(TRIGGER) !== null || 'trigger missing';
			}
		},
		{
			id: 'open-renders-lists',
			description: 'the open panel shows one toggle per list, Favourites pinned first and pressed',
			onlyFixtures: ['open'],
			check: ({ contract, root, props }) => {
				if (contract.open !== 'true') return `open=${contract.open}`;
				const toggles = root.querySelectorAll(TOGGLE);
				if (toggles.length !== props.lists.length)
					return `expected ${props.lists.length} toggles, saw ${toggles.length}`;
				if (contract['default-first'] !== 'true') return 'Favourites not pinned first';
				if (contract.members !== 'Favourites|To try') return `members=${contract.members}`;
				const pressed = [...toggles].filter((t) => t.getAttribute('aria-pressed') === 'true');
				return pressed.length === 2 || `expected 2 pressed toggles, saw ${pressed.length}`;
			}
		},
		{
			id: 'click-opens',
			description: 'clicking the trigger opens the panel',
			onlyFixtures: ['open-via-click'],
			check: ({ contract, root }) =>
				(contract.open === 'true' && root.querySelector('.panel') !== null) ||
				`open=${contract.open}`
		},
		{
			id: 'toggle-wires',
			description: 'clicking an unticked row toggles that list and dismisses the panel',
			onlyFixtures: ['toggle-member'],
			check: ({ contract, root }) => {
				if (contract.toggled !== 'Weeknight dinners') return `toggled=${contract.toggled}`;
				if (contract.open !== 'false') return `panel still open after toggle: open=${contract.open}`;
				return root.querySelector('.panel') === null || 'panel should be dismissed after a toggle';
			}
		},
		{
			id: 'create-wires',
			description: 'creating echoes the typed name and dismisses the panel',
			onlyFixtures: ['create'],
			check: ({ contract, root }) => {
				if (contract.created !== 'Brunch') return `created=${contract.created}`;
				if (contract.open !== 'false') return `panel still open after a create: open=${contract.open}`;
				return root.querySelector('.panel') === null || 'panel should be dismissed after a create';
			}
		},
		{
			id: 'failed-toggle-stays-open',
			description: 'a rejected toggle leaves the panel mounted and open',
			onlyFixtures: ['toggle-error'],
			check: ({ contract, root }) => {
				if (contract.open !== 'true') return 'panel dismissed after a failed toggle';
				return root.querySelector('.panel') !== null || 'panel missing after a failed toggle';
			}
		},
		{
			id: 'long-names-render',
			description: 'every overlong list still renders as a labelled toggle',
			onlyFixtures: ['long-names'],
			check: ({ root, props }) => {
				const toggles = root.querySelectorAll(TOGGLE);
				return (
					toggles.length === props.lists.length ||
					`expected ${props.lists.length} toggles, saw ${toggles.length}`
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
