import RowListPicker, { type RowListPickerProps } from '$lib/components/RowListPicker.svelte';
import type { ListMembership, ListPanelApi } from '$lib/api/lists';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = RowListPickerProps;

const TRIGGER = '.add-trigger';
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
function stubApi(
	lists: ListMembership[],
	opts: { failFetch?: boolean; failAdd?: boolean; delayMs?: number } = {}
): ListPanelApi {
	let next = 0;
	return {
		fetchRecipeLists: () =>
			new Promise((resolve, reject) => {
				const settle = () =>
					opts.failFetch
						? reject(new Error('stub: lists unavailable'))
						: resolve(lists.map((l) => ({ ...l })));
				if (opts.delayMs) setTimeout(settle, opts.delayMs);
				else settle();
			}),
		addRecipeToList: async () => {
			if (opts.failAdd) throw new Error('stub: could not add');
		},
		removeRecipeFromList: async () => {},
		createList: async (name: string) => ({ id: `created-${next++}`, name, is_default: false })
	};
}

const THREE_LISTS = [
	membership('fav', 'Favourites', true, true),
	membership('wk', 'Weeknight', false, false),
	membership('tt', 'To try', false, true)
];

function props(
	lists: ListMembership[],
	extra: Partial<Props> = {},
	opts: { failFetch?: boolean; failAdd?: boolean; delayMs?: number } = {}
): Props {
	return {
		recipeId: 'a0054f3d-3f99-4502-aa48-dc933c13fab8',
		recipeName: 'Dal Makhani',
		api: stubApi(lists, opts),
		viewport: { h: 10_000 },
		...extra
	};
}

const unit: VerifiableUnit<Props> = {
	id: 'row-list-picker',
	title: 'Row list picker',
	description:
		'The per-row [+] on a recipe row: a compact trigger opening a lazy-fetched list panel (membership toggles + create) that dismisses on a successful choice, flipped above the trigger when the fold is near.',
	kind: 'component',
	component: RowListPicker,
	propsSchema: z.object({
		recipeId: z.string().min(1),
		recipeName: z.string().min(1),
		viewport: z.object({ h: z.number() }).optional()
	}),
	fixtures: [
		{
			id: 'closed',
			description: 'the resting [+] trigger, panel collapsed, nothing fetched',
			props: props(THREE_LISTS)
		},
		{
			id: 'open-via-click',
			description: 'clicking the trigger opens the panel and lazy-fetches memberships',
			props: props(THREE_LISTS),
			act: async ({ click, wait }) => {
				click(TRIGGER);
				await wait(0);
			}
		},
		{
			id: 'toggle-member',
			description: 'clicking an unticked list adds the recipe and dismisses the panel',
			props: props(THREE_LISTS),
			act: async ({ click, wait }) => {
				click(TRIGGER);
				await wait(0);
				click(SECOND_ROW);
				await wait(0);
			}
		},
		{
			id: 'toggle-error',
			description: 'a failed add leaves the panel open so the row can be retried',
			props: props(THREE_LISTS, {}, { failAdd: true }),
			act: async ({ click, wait }) => {
				click(TRIGGER);
				await wait(0);
				click(SECOND_ROW);
				await wait(0);
			}
		},
		{
			id: 'create',
			description: 'creating a list from the row adds the recipe to it and dismisses the panel',
			props: props(THREE_LISTS),
			act: async ({ click, type, wait }) => {
				click(TRIGGER);
				await wait(0);
				type(CREATE_INPUT, 'Weekend baking');
				click(CREATE_BTN);
				await wait(0);
			}
		},
		{
			id: 'create-error',
			description: 'a created list whose add fails is left unticked and the panel stays open',
			props: props(THREE_LISTS, {}, { failAdd: true }),
			act: async ({ click, type, wait }) => {
				click(TRIGGER);
				await wait(0);
				type(CREATE_INPUT, 'Weekend baking');
				click(CREATE_BTN);
				await wait(0);
			}
		},
		{
			id: 'load-error',
			description: 'a failed membership fetch shows the error note, trigger still labelled',
			props: props([], {}, { failFetch: true }),
			act: async ({ click, wait }) => {
				click(TRIGGER);
				await wait(0);
			}
		},
		{
			id: 'flip-up',
			description: 'a stubbed shallow viewport forces the panel above the trigger',
			props: props(THREE_LISTS, { viewport: { h: 100 } }),
			act: async ({ click, wait }) => {
				click(TRIGGER);
				await wait(0);
			}
		},
		{
			id: 'slow-load-long-names',
			description:
				'probe: twelve overlong unicode names on a slow fetch — the loading phase is observable and nothing breaks',
			probe: true,
			props: props(
				Array.from({ length: 12 }, (_, i) =>
					membership(
						`x${i}`,
						`Très Long Collection Name Number ${i} — 你好 ${'spaghetti '.repeat(3)}`,
						i === 0,
						i % 2 === 0
					)
				),
				{},
				{ delayMs: 60 }
			),
			act: async ({ click, wait }) => {
				click(TRIGGER);
				await wait(0);
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: props(THREE_LISTS)
		}
	],
	invariants: [
		{
			id: 'closed-hides-panel',
			description: 'collapsed: the labelled trigger only, no panel, nothing fetched',
			onlyFixtures: ['closed'],
			check: ({ contract, root }) => {
				if (contract.open !== 'false') return `open=${contract.open}`;
				if (root.querySelector('.panel')) return 'panel should not render while closed';
				if (contract.lists !== '0') return `lists fetched while closed: ${contract.lists}`;
				const trigger = root.querySelector(TRIGGER);
				return (
					trigger?.getAttribute('aria-label') === 'Add Dal Makhani to a list' ||
					'trigger missing or unlabelled'
				);
			}
		},
		{
			id: 'click-opens-and-fetches',
			description: 'the first open lazy-fetches: panel, rows, Favourites first, placed below',
			onlyFixtures: ['open-via-click'],
			check: ({ contract, root }) => {
				if (contract.open !== 'true') return `open=${contract.open}`;
				if (contract.phase !== 'ready') return `phase=${contract.phase}`;
				const rows = root.querySelectorAll(ROW).length;
				if (rows !== 3) return `expected 3 rows, saw ${rows}`;
				if (contract['default-first'] !== 'true') return 'Favourites not pinned first';
				return contract.placement === 'down' || `placement=${contract.placement}`;
			}
		},
		{
			id: 'toggle-wires',
			description: 'toggling an unticked list adds the recipe and dismisses the panel',
			onlyFixtures: ['toggle-member'],
			check: ({ contract, root }) => {
				if (contract.toggled !== 'Weeknight') return `toggled=${contract.toggled}`;
				if (!contract.members.includes('Weeknight')) return `members=${contract.members}`;
				if (contract.open !== 'false') return `panel still open after toggle: open=${contract.open}`;
				return root.querySelector('.panel') === null || 'panel should be dismissed after a toggle';
			}
		},
		{
			id: 'failed-toggle-stays-open',
			description: 'a failed add keeps the panel open and the row unticked',
			onlyFixtures: ['toggle-error'],
			check: ({ contract, root }) => {
				if (contract.open !== 'true') return 'panel dismissed after a failed toggle';
				if (contract.members.includes('Weeknight')) return `members=${contract.members}`;
				const row = root.querySelector(SECOND_ROW);
				return row?.getAttribute('aria-pressed') === 'false' || 'row ticked despite the failure';
			}
		},
		{
			id: 'created-contains',
			description: 'a created list appears as a ticked row containing the recipe',
			onlyFixtures: ['create'],
			check: ({ contract }) => {
				if (contract.created !== 'Weekend baking') return `created=${contract.created}`;
				if (!contract.members.includes('Weekend baking')) return `members=${contract.members}`;
				if (Number(contract.lists) !== 4) return `lists=${contract.lists} expected 4`;
				return contract.open === 'false' || 'panel still open after a create';
			}
		},
		{
			id: 'failed-create-stays-open',
			description: 'the created list is shown unticked and the panel stays open for a retry',
			onlyFixtures: ['create-error'],
			check: ({ contract, root }) => {
				if (contract.created !== 'Weekend baking') return `created=${contract.created}`;
				if (contract.members.includes('Weekend baking')) return `members=${contract.members}`;
				if (contract.open !== 'true') return 'panel dismissed after a failed create';
				return root.querySelector('.panel') !== null || 'panel missing after a failed create';
			}
		},
		{
			id: 'error-state',
			description: 'the error state shows the note, no rows and no create field',
			onlyFixtures: ['load-error'],
			check: ({ contract, root }) => {
				if (contract.phase !== 'error') return `phase=${contract.phase}`;
				if (root.querySelector(ROW)) return 'list rows rendered in the error state';
				if (root.querySelector(CREATE_INPUT)) return 'create field rendered in the error state';
				return (
					(root.textContent ?? '').includes('Couldn’t load your lists') || 'error message missing'
				);
			}
		},
		{
			id: 'flips-up',
			description: 'with the fold directly below, the panel is placed above the trigger',
			onlyFixtures: ['flip-up'],
			check: ({ contract, root }) => {
				if (contract.placement !== 'up') return `placement=${contract.placement}`;
				return root.querySelector('.panel.up') !== null || 'panel missing the .up placement';
			}
		},
		{
			id: 'loading-observable',
			description: 'while the slow fetch is in flight the panel shows the loading note, no rows',
			onlyFixtures: ['slow-load-long-names'],
			check: ({ contract, root }) => {
				if (contract.phase !== 'loading') return `phase=${contract.phase}`;
				if (root.querySelector(ROW)) return 'rows rendered before the fetch resolved';
				return (root.textContent ?? '').includes('Loading lists…') || 'loading note missing';
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
