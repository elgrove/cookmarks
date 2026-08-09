import ListsIndex, { type ListsIndexProps } from '$lib/components/ListsIndex.svelte';
import type { ListSummary } from '$lib/api/lists';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ListsIndexProps;

function list(over: Partial<ListSummary> = {}): ListSummary {
	return {
		id: over.id ?? 'l1',
		name: over.name ?? 'A list',
		is_default: over.is_default ?? false,
		recipe_count: over.recipe_count ?? 0
	};
}

const lists: ListSummary[] = [
	list({ id: 'fav', name: 'Favourites', is_default: true, recipe_count: 5 }),
	list({ id: 'wk', name: 'Weeknight dinners', recipe_count: 12 }),
	list({ id: 'tt', name: 'To try', recipe_count: 3 })
];

const SEARCH = '.search-input';
const NEW_LIST_BTN = '.new-list-btn';
const CREATE_INPUT = '.modal-input';
const CREATE_BTN = '.create-btn';
const RENAME_BTN = '.rename-btn';
const RENAME_INPUT = '.rename-input';
const RENAME_SAVE = '.rename-save';
const DELETE_BTN = '.delete-btn';
const CONFIRM_DELETE = '.confirm-delete';

const unit: VerifiableUnit<Props> = {
	id: 'lists-index',
	title: 'Lists index',
	description:
		'The collection of lists: a searchable card grid with the default Favourites pinned first, a create-new field, a count, and per-card rename / delete (never on the default).',
	kind: 'component',
	component: ListsIndex,
	fixtures: [
		{
			id: 'populated',
			description: 'a grid of lists, the queue card pinned first, Favourites next',
			props: { lists, queueCount: 3 }
		},
		{
			id: 'empty',
			description: 'no lists yet — the calm empty state',
			props: { lists: [] }
		},
		{
			id: 'search',
			description: 'typing narrows the grid by name',
			props: { lists },
			act: ({ type }) => type(SEARCH, 'week')
		},
		{
			id: 'create',
			description: 'the New-list button opens a modal; naming it and pressing Create fires the handler',
			props: { lists },
			act: ({ click, type }) => {
				click(NEW_LIST_BTN);
				type(CREATE_INPUT, 'Brunch');
				click(CREATE_BTN);
			}
		},
		{
			id: 'open-create-modal',
			description: 'the New-list button opens the create modal',
			props: { lists },
			act: ({ click }) => click(NEW_LIST_BTN)
		},
		{
			id: 'rename',
			description: 'renaming the first custom list fires the rename handler',
			props: { lists },
			act: ({ click, type }) => {
				click(RENAME_BTN);
				type(RENAME_INPUT, 'Quick meals');
				click(RENAME_SAVE);
			}
		},
		{
			id: 'delete',
			description: 'deleting a custom list takes a confirm step, then fires the delete handler',
			props: { lists },
			act: ({ click }) => {
				click(DELETE_BTN);
				click(CONFIRM_DELETE);
			}
		},
		{
			id: 'long-names',
			description: 'probe: many lists with overlong unicode names all render',
			probe: true,
			props: {
				lists: Array.from({ length: 9 }, (_, i) =>
					list({
						id: `x${i}`,
						name: `Très Long Collection — ${i} — 你好 ${'noodles '.repeat(3)}`,
						is_default: i === 0,
						recipe_count: i * 7
					})
				)
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { lists }
		}
	],
	invariants: [
		{
			id: 'grid-rendered',
			description: 'every list renders as a card, Favourites pinned first',
			onlyFixtures: ['populated'],
			check: ({ contract, root, props }) => {
				const cards = root.querySelectorAll('.card');
				if (cards.length !== props.lists.length)
					return `expected ${props.lists.length} cards, saw ${cards.length}`;
				if (contract.count !== String(props.lists.length)) return `count=${contract.count}`;
				if (contract['default-first'] !== 'true') return 'Favourites not pinned first';
				return contract.first === 'Favourites' || `first=${contract.first}`;
			}
		},
		{
			id: 'queue-card-pinned-first',
			description: 'the reading-queue card leads the grid, ahead of the default list',
			onlyFixtures: ['populated'],
			check: ({ contract, root }) => {
				if (contract['queue-count'] !== '3') return `queue-count=${contract['queue-count']}`;
				const first = root.querySelector('.grid > li');
				if (!first?.querySelector('.queue-card')) return 'first grid cell is not the queue card';
				const href = first.querySelector('a')?.getAttribute('href') ?? '';
				return href === '/lists/reading-queue' || `queue card href=${href}`;
			}
		},
		{
			id: 'whole-card-clickable',
			description:
				'each card exposes exactly one stretched nav link to its detail page (whole surface clickable)',
			onlyFixtures: ['populated'],
			check: ({ root }) => {
				const cards = [...root.querySelectorAll('.card')];
				for (const card of cards) {
					const links = card.querySelectorAll('a[href^="/lists/"]');
					if (links.length !== 1)
						return `card has ${links.length} nav link(s), expected exactly 1`;
					const href = links[0].getAttribute('href') ?? '';
					if (!/^\/lists\/.+/.test(href)) return `nav href not a list detail page: ${href}`;
				}
				return true;
			}
		},
		{
			id: 'actions-not-nested-in-link',
			description:
				'Rename / Delete are real controls outside the nav link, so they click without navigating',
			onlyFixtures: ['populated'],
			check: ({ root }) => {
				if (root.querySelector('a button')) return 'a button is nested inside the nav link';
				const card = [...root.querySelectorAll('.card')].find(
					(c) => c.querySelector('.rename-btn') !== null
				);
				if (!card) return 'no custom card with action buttons found';
				if (!card.querySelector('.rename-btn')) return 'rename button missing';
				return card.querySelector('.delete-btn') !== null || 'delete button missing';
			}
		},
		{
			id: 'empty-state',
			description: 'no lists shows the empty message and no cards',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.card')) return 'no cards expected';
				return (root.textContent ?? '').includes('No lists yet') || 'empty message missing';
			}
		},
		{
			id: 'search-narrows',
			description: 'searching filters the grid and records the query',
			onlyFixtures: ['search'],
			check: ({ contract }) => {
				if (contract.query !== 'week') return `query=${contract.query}`;
				if (contract.count !== '1') return `count=${contract.count}`;
				return contract.first === 'Weeknight dinners' || `first=${contract.first}`;
			}
		},
		{
			id: 'create-wires',
			description: 'creating echoes the typed name into the contract',
			onlyFixtures: ['create'],
			check: ({ contract }) => contract.created === 'Brunch' || `created=${contract.created}`
		},
		{
			id: 'create-modal-opens',
			description: 'clicking New list reveals the create dialog with a name field',
			onlyFixtures: ['open-create-modal'],
			check: ({ root }) => {
				if (!root.querySelector('.modal[role="dialog"]')) return 'create dialog did not open';
				return root.querySelector('.modal-input') !== null || 'no name field in the create dialog';
			}
		},
		{
			id: 'rename-wires',
			description: 'renaming a custom list echoes the new name into the contract',
			onlyFixtures: ['rename'],
			check: ({ contract }) => contract.renamed === 'Quick meals' || `renamed=${contract.renamed}`
		},
		{
			id: 'delete-wires',
			description: 'deleting the first custom list records its id',
			onlyFixtures: ['delete'],
			check: ({ contract }) => contract.deleted === 'wk' || `deleted=${contract.deleted}`
		},
		{
			id: 'long-names-render',
			description: 'every overlong list still renders as a card',
			onlyFixtures: ['long-names'],
			check: ({ root, props }) => {
				const cards = root.querySelectorAll('.card');
				return cards.length === props.lists.length || `saw ${cards.length} cards`;
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
