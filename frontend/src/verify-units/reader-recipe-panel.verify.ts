import ReaderRecipePanel, {
	type PanelApi,
	type ReaderRecipePanelProps
} from '$lib/components/ReaderRecipePanel.svelte';
import type { ListMembership } from '$lib/api/lists';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

const ROW = '.lists .list-toggle';
const SECOND_ROW = '.lists li:nth-child(2) .list-toggle';
const CREATE_INPUT = '.create-input';
const CREATE_BTN = '.create-btn';

function membership(
	id: string,
	name: string,
	is_default: boolean,
	contains: boolean
): ListMembership {
	return { id, name, is_default, contains };
}

/** A stub of the list endpoints: resolves from the given memberships, no network. */
function stubApi(lists: ListMembership[], opts: { failFetch?: boolean } = {}): PanelApi {
	let next = 0;
	return {
		fetchRecipeLists: async () => {
			if (opts.failFetch) throw new Error('stub: lists unavailable');
			return lists.map((l) => ({ ...l }));
		},
		addRecipeToList: async () => {},
		removeRecipeFromList: async () => {},
		createList: async (name: string) => ({ id: `created-${next++}`, name, is_default: false })
	};
}

const FOUR_LISTS = [
	membership('l1', 'Favourites', true, true),
	membership('l2', 'Weeknight', false, false),
	membership('l3', 'To try', false, true),
	membership('l4', 'Baking', false, false)
];

const anchor = { x: 300, y: 180, w: 24, h: 24 };

function props(
	lists: ListMembership[],
	extra: Partial<ReaderRecipePanelProps> = {},
	opts: { failFetch?: boolean } = {}
): ReaderRecipePanelProps {
	return {
		recipeId: 'a0054f3d-3f99-4502-aa48-dc933c13fab8',
		recipeName: "Rosetta's Trofie with Basil Sauce",
		anchor,
		onClose: () => {},
		api: stubApi(lists, opts),
		...extra
	};
}

const unit: VerifiableUnit<ReaderRecipePanelProps> = {
	id: 'reader-recipe-panel',
	title: 'Reader recipe panel',
	description:
		'The save-to-list popover the EPUB reader opens from an injected control beside a matched recipe title: list membership toggles, new-list creation, and a link to the extracted recipe. A settled choice dismisses it.',
	kind: 'component',
	component: ReaderRecipePanel,
	propsSchema: z.object({
		recipeId: z.string().min(1),
		recipeName: z.string().min(1),
		anchor: z.object({ x: z.number(), y: z.number(), w: z.number(), h: z.number() })
	}),
	fixtures: [
		{
			id: 'populated',
			description: 'four lists, Favourites first, two containing the recipe',
			props: props(FOUR_LISTS),
			act: ({ wait }) => wait(0)
		},
		{
			id: 'empty-lists',
			description: 'no lists at all still offers the create field and the recipe link',
			props: props([]),
			act: ({ wait }) => wait(0)
		},
		{
			id: 'load-error',
			description: 'a failed membership fetch reports the error instead of an empty panel',
			props: props([], {}, { failFetch: true }),
			act: ({ wait }) => wait(0)
		},
		{
			id: 'toggle-on',
			description: 'clicking a list the recipe is not in adds it, ticks the row and dismisses',
			props: props(FOUR_LISTS),
			act: async ({ wait, click }) => {
				await wait(0);
				click(SECOND_ROW);
				await wait(0);
			}
		},
		{
			id: 'toggle-favourite',
			description: 'untoggling the Favourites row reports the change for star sync',
			props: props(FOUR_LISTS),
			act: async ({ wait, click }) => {
				await wait(0);
				click(`.lists li:first-child .list-toggle`);
				await wait(0);
			}
		},
		{
			id: 'create-list',
			description: 'creating a list adds the recipe to it straight away, then dismisses',
			props: props(FOUR_LISTS),
			act: async ({ wait, click, type }) => {
				await wait(0);
				type(CREATE_INPUT, 'Weekend baking');
				click(CREATE_BTN);
				await wait(0);
			}
		},
		{
			id: 'long-name-many-lists',
			description: 'probe: an overlong recipe name and 24 lists must not break the popover',
			probe: true,
			props: props(
				[
					membership('l0', 'Favourites', true, false),
					...Array.from({ length: 23 }, (_, i) =>
						membership(`lx${i}`, `A fairly long list name number ${i + 1}`, false, i % 3 === 0)
					)
				],
				{
					recipeName:
						'A recipe with an unusually long descriptive name that keeps going and going past one line'
				}
			),
			act: ({ wait }) => wait(0)
		},
		{
			id: 'no-default-list',
			description: 'probe: memberships without a default list render without a star, nothing breaks',
			probe: true,
			props: props([membership('l5', 'Weeknight', false, true)]),
			act: ({ wait }) => wait(0)
		},
		{
			id: 'contract-lie',
			description: 'expectFail: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: props(FOUR_LISTS),
			act: ({ wait }) => wait(0)
		}
	],
	invariants: [
		{
			id: 'phase',
			description: 'the panel settles to ready, or to error when the membership fetch fails',
			check: ({ contract, fixture }) => {
				const want = fixture.id === 'load-error' ? 'error' : 'ready';
				return contract.phase === want || `phase=${contract.phase} expected ${want}`;
			}
		},
		{
			id: 'rows-match-contract',
			description: 'rendered list rows equal the contract lists count',
			check: ({ contract, root }) => {
				const rows = root.querySelectorAll(ROW).length;
				return Number(contract.lists) === rows || `lists=${contract.lists} rows=${rows}`;
			}
		},
		{
			id: 'members-reflect-rows',
			description: 'the members contract is exactly the ticked rows, in order',
			check: ({ contract, root }) => {
				const ticked = [...root.querySelectorAll(ROW)]
					.filter((r) => r.getAttribute('aria-pressed') === 'true')
					.map((r) => r.querySelector('.name')?.textContent?.trim() ?? '')
					.join('|');
				return contract.members === ticked || `members=${contract.members} rows say ${ticked}`;
			}
		},
		{
			id: 'default-first',
			description: 'the default-first contract agrees with the starred first row',
			check: ({ contract, root }) => {
				const starred = root.querySelector(`.lists li:first-child .list-toggle .star`) !== null;
				return (
					contract['default-first'] === String(starred) ||
					`default-first=${contract['default-first']} but first-row star=${starred}`
				);
			}
		},
		{
			id: 'error-shows-no-rows',
			description: 'the error state renders no rows and no create field — only the message',
			onlyFixtures: ['load-error'],
			check: ({ root }) => {
				if (root.querySelector(ROW)) return 'list rows rendered in the error state';
				if (root.querySelector(CREATE_INPUT)) return 'create field rendered in the error state';
				return (
					(root.textContent ?? '').includes('Couldn’t load your lists') || 'error message missing'
				);
			}
		},
		{
			id: 'toggle-adds',
			description: 'toggling an unticked list ticks it, echoes the toggle and dismisses',
			onlyFixtures: ['toggle-on'],
			check: ({ contract, root }) => {
				if (contract.toggled !== 'Weeknight') return `toggled=${contract.toggled}`;
				const row = root.querySelector(SECOND_ROW);
				if (row?.getAttribute('aria-pressed') !== 'true') return 'row not ticked after toggle';
				if (!contract.members.includes('Weeknight')) return `members=${contract.members}`;
				return contract.dismissed === 'true' || 'popover not dismissed after a toggle';
			}
		},
		{
			id: 'favourite-sync',
			description: 'toggling the default row reports the favourite change for the in-book star',
			onlyFixtures: ['toggle-favourite'],
			check: ({ contract }) => {
				if (contract.toggled !== 'Favourites') return `toggled=${contract.toggled}`;
				return contract['fav-change'] === 'false' || `fav-change=${contract['fav-change']}`;
			}
		},
		{
			id: 'created-contains',
			description: 'a created list appears as a ticked row containing the recipe',
			onlyFixtures: ['create-list'],
			check: ({ contract }) => {
				if (contract.created !== 'Weekend baking') return `created=${contract.created}`;
				if (!contract.members.includes('Weekend baking')) return `members=${contract.members}`;
				if (Number(contract.lists) !== 5) return `lists=${contract.lists} expected 5`;
				return contract.dismissed === 'true' || 'popover not dismissed after a create';
			}
		},
		{
			id: 'view-link',
			description: 'the panel links to the extracted recipe',
			check: ({ root, props }) => {
				const href = root.querySelector('a.view')?.getAttribute('href');
				const want = `/recipes/${props.recipeId}`;
				return href === want || `view href=${href} expected ${want}`;
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
