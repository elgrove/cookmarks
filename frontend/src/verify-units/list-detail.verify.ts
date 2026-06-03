import ListDetail, { type ListDetailData } from '$lib/components/ListDetail.svelte';
import type { RecipeRowData } from '$lib/components/RecipeRow.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = {
	list: ListDetailData;
	onRename?: (name: string) => void;
	onDelete?: () => void;
	onRemoveRecipe?: (recipeId: string) => void;
};

function recipe(over: Partial<RecipeRowData> = {}): RecipeRowData {
	return {
		id: over.id ?? 'r1',
		name: over.name ?? 'Dal Makhani',
		bookId: over.bookId ?? 'b1',
		bookTitle: over.bookTitle ?? 'Made in India',
		bookAuthor: over.bookAuthor ?? 'Meera Sodha',
		keywords: over.keywords ?? ['lentils', 'vegetarian']
	};
}

const recipes: RecipeRowData[] = [
	recipe({ id: 'r1', name: 'Dal Makhani' }),
	recipe({ id: 'r2', name: 'Tarka Dal', keywords: ['lentils'] })
];

function customList(over: Partial<ListDetailData> = {}): ListDetailData {
	return {
		id: over.id ?? 'wk',
		name: over.name ?? 'Weeknight dinners',
		isDefault: over.isDefault ?? false,
		recipeCount: over.recipeCount ?? (over.recipes ?? recipes).length,
		recipes: over.recipes ?? recipes
	};
}

const ROW = '.rows .row';
const REMOVE = '.remove';
const RENAME_BTN = '.rename-btn';
const RENAME_INPUT = '.rename-input';
const RENAME_SAVE = '.rename-save';
const DELETE_BTN = '.delete-btn';
const CONFIRM_DELETE = '.confirm-delete';

const unit: VerifiableUnit<Props> = {
	id: 'list-detail',
	title: 'List detail',
	description:
		'A single list opened: a masthead with rename / delete (suppressed on the default Favourites) and the list’s recipes as a text-first index, each removable.',
	kind: 'component',
	component: ListDetail,
	fixtures: [
		{
			id: 'populated',
			description: 'a custom list with its recipes and the rename / delete actions',
			props: { list: customList() }
		},
		{
			id: 'empty',
			description: 'a list with no recipes — the calm empty state',
			props: { list: customList({ recipes: [] }) }
		},
		{
			id: 'default-list',
			description: 'the default Favourites list hides rename / delete',
			props: { list: customList({ id: 'fav', name: 'Favourites', isDefault: true }) }
		},
		{
			id: 'remove-recipe',
			description: 'removing the first recipe fires the remove handler',
			props: { list: customList() },
			act: ({ click }) => click(REMOVE)
		},
		{
			id: 'rename',
			description: 'renaming the list fires the rename handler',
			props: { list: customList() },
			act: ({ click, type }) => {
				click(RENAME_BTN);
				type(RENAME_INPUT, 'Quick meals');
				click(RENAME_SAVE);
			}
		},
		{
			id: 'delete',
			description: 'deleting takes a confirm step, then fires the delete handler',
			props: { list: customList() },
			act: ({ click }) => {
				click(DELETE_BTN);
				click(CONFIRM_DELETE);
			}
		},
		{
			id: 'long-content',
			description: 'probe: overlong unicode recipe names and many keywords all render',
			probe: true,
			props: {
				list: customList({
					recipes: [
						recipe({
							id: 'long',
							name: 'Slow-Roasted Pork Shoulder with Crème Fraîche, Pommes Purée & Sauce Gribiche — 你好',
							keywords: ['pork', 'slow', 'french', 'roast', 'dinner', 'feast', 'sunday']
						}),
						recipe({ id: 'r2', name: 'Tarka Dal' })
					]
				})
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { list: customList() }
		}
	],
	invariants: [
		{
			id: 'recipes-rendered',
			description: 'every recipe renders as a row, with rename / delete available',
			onlyFixtures: ['populated'],
			check: ({ contract, root, props }) => {
				const rows = root.querySelectorAll(ROW);
				if (rows.length !== props.list.recipes.length)
					return `expected ${props.list.recipes.length} rows, saw ${rows.length}`;
				if (contract.count !== String(props.list.recipes.length)) return `count=${contract.count}`;
				if (contract.empty !== 'false') return `empty=${contract.empty}`;
				if (!root.querySelector(RENAME_BTN)) return 'rename action missing on a custom list';
				return root.querySelector(DELETE_BTN) !== null || 'delete action missing on a custom list';
			}
		},
		{
			id: 'empty-state',
			description: 'a list with no recipes shows the empty message and no rows',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector(ROW)) return 'no rows expected';
				return (root.textContent ?? '').includes('No recipes in this list') || 'empty message missing';
			}
		},
		{
			id: 'default-hides-actions',
			description: 'the default Favourites list exposes no rename / delete',
			onlyFixtures: ['default-list'],
			check: ({ contract, root }) => {
				if (contract.default !== 'true') return `default=${contract.default}`;
				if (root.querySelector(RENAME_BTN)) return 'rename must be hidden on the default list';
				return root.querySelector(DELETE_BTN) === null || 'delete must be hidden on the default list';
			}
		},
		{
			id: 'remove-wires',
			description: 'removing the first recipe records its id',
			onlyFixtures: ['remove-recipe'],
			check: ({ contract }) => contract.removed === 'r1' || `removed=${contract.removed}`
		},
		{
			id: 'rename-wires',
			description: 'renaming echoes the new name into the contract',
			onlyFixtures: ['rename'],
			check: ({ contract }) => contract.renamed === 'Quick meals' || `renamed=${contract.renamed}`
		},
		{
			id: 'delete-wires',
			description: 'confirming a delete records it',
			onlyFixtures: ['delete'],
			check: ({ contract }) => contract.deleted === 'true' || `deleted=${contract.deleted}`
		},
		{
			id: 'long-content-renders',
			description: 'every overlong recipe still renders as a row',
			onlyFixtures: ['long-content'],
			check: ({ root, props }) => {
				const rows = root.querySelectorAll(ROW);
				return rows.length === props.list.recipes.length || `saw ${rows.length} rows`;
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
