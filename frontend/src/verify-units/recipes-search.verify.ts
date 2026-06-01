import RecipesSearch, { type RecipesSearchProps } from '$lib/components/RecipesSearch.svelte';
import type { RecipeSummary } from '$lib/api/recipes';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = RecipesSearchProps;

function recipe(over: Partial<RecipeSummary> = {}): RecipeSummary {
	return {
		id: over.id ?? 'r1',
		name: over.name ?? 'Dal Makhani',
		book_id: over.book_id ?? 'b1',
		book_title: over.book_title ?? 'Made in India',
		book_author: over.book_author ?? 'Meera Sodha',
		keywords: over.keywords ?? ['lentils', 'vegetarian']
	};
}

const twoResults: RecipeSummary[] = [
	recipe({ id: 'r1', name: 'Dal Makhani' }),
	recipe({ id: 'r2', name: 'Tarka Dal', keywords: ['lentils'] })
];

const chips = [
	{ name: 'quick', recipe_count: 9 },
	{ name: 'vegetarian', recipe_count: 21 },
	{ name: 'baking', recipe_count: 14 }
];

// Facets re-ranked around a selected "quick": the chosen keyword is gone (the
// server drops selected keywords), so the component must pin it back on top.
const cooccurring = [
	{ name: 'weeknight', recipe_count: 7 },
	{ name: 'one-pot', recipe_count: 4 }
];

const SEARCH = 'input[type="search"]';
const CHIP = '.chip';

const unit: VerifiableUnit<Props> = {
	id: 'recipes-search',
	title: 'Recipes search',
	description:
		'Server-driven recipe search: a keyword box + keyword/book/author filters, a result count, paginated text-first rows, and a resting state that is empty until a query.',
	kind: 'component',
	component: RecipesSearch,
	fixtures: [
		{
			id: 'resting',
			description: 'no query and no filters — the calm resting prompt, empty until a query',
			props: { status: 'resting', keywords: chips }
		},
		{
			id: 'results',
			description: 'a query with results: count, rows and pagination',
			props: {
				status: 'results',
				criteria: { q: 'dal', limit: 2, offset: 0 },
				results: { total: 5, items: twoResults, facets: chips },
				keywords: chips
			}
		},
		{
			id: 'no-results',
			description: 'a query that matches nothing shows the calm no-results state',
			props: {
				status: 'empty',
				criteria: { q: 'zzzznope' },
				results: { total: 0, items: [], facets: [] },
				keywords: chips
			}
		},
		{
			id: 'keyword-selected',
			description: 'a pre-selected keyword chip renders pressed and counts as a query',
			props: {
				status: 'results',
				criteria: { keywords: ['quick'] },
				results: { total: 1, items: [recipe({ keywords: ['quick'] })], facets: chips },
				keywords: chips
			}
		},
		{
			id: 'facet-narrowed',
			description:
				'a selected keyword absent from the facets is still pinned, pressed and deselectable',
			props: {
				status: 'results',
				criteria: { keywords: ['quick'] },
				results: { total: 1, items: [recipe({ keywords: ['quick'] })], facets: cooccurring },
				// The facet list (re-ranked by the server) no longer contains the
				// selected "quick" — the component must pin it on top.
				keywords: cooccurring
			}
		},
		{
			id: 'clear-selection',
			description: 'the clear button deselects every chosen keyword at once',
			props: {
				status: 'results',
				criteria: { keywords: ['quick', 'baking'] },
				results: { total: 1, items: [recipe({ keywords: ['quick'] })], facets: chips },
				keywords: chips
			},
			act: ({ click }) => click('.clear-kw')
		},
		{
			id: 'type-query',
			description: 'typing into the box echoes into the contract and activates the search',
			props: { status: 'resting', keywords: chips },
			act: ({ type }) => type(SEARCH, 'anchovy')
		},
		{
			id: 'toggle-chip',
			description: 'clicking a keyword chip selects it (aria-pressed) and records it as a filter',
			props: { status: 'resting', keywords: chips },
			act: ({ click }) => click(CHIP)
		},
		{
			id: 'long-name',
			description: 'probe: an overlong unicode name with many keywords renders in full',
			probe: true,
			props: {
				status: 'results',
				criteria: { q: 'x' },
				results: {
					total: 1,
					items: [
						recipe({
							id: 'long',
							name: 'Slow-Roasted Pork Shoulder with Crème Fraîche, Pommes Purée, Sauce Gribiche & Far More Than Will Ever Fit On A Single Line — 你好',
							keywords: ['pork', 'slow', 'french', 'roast', 'dinner', 'feast', 'sunday']
						})
					],
					facets: chips
				},
				keywords: chips
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: {
				status: 'results',
				results: { total: 1, items: [recipe()], facets: [] },
				keywords: chips
			}
		}
	],
	invariants: [
		{
			id: 'resting-empty',
			description: 'the resting state is inactive and shows no results',
			onlyFixtures: ['resting'],
			check: ({ contract, root }) => {
				if (contract.status !== 'resting' || contract.resting !== 'true')
					return `status=${contract.status} resting=${contract.resting}`;
				if (contract.active !== 'false') return `active=${contract.active}`;
				if (contract.shown !== '0' || contract.total !== '0')
					return `shown=${contract.shown} total=${contract.total}`;
				return root.querySelector('.rows') === null || 'resting should render no result rows';
			}
		},
		{
			id: 'results-rendered',
			description: 'every result item renders as a row, with a correct count and pager',
			onlyFixtures: ['results'],
			check: ({ contract, root, props }) => {
				const items = props.results?.items ?? [];
				if (Number(contract.shown) !== items.length) return `shown=${contract.shown}`;
				const rows = root.querySelectorAll('.rows .row').length;
				if (rows !== items.length) return `expected ${items.length} rows, saw ${rows}`;
				if (!(root.textContent ?? '').includes('1–2 of 5')) return 'count label missing';
				const buttons = root.querySelectorAll('.pager .page-btn');
				if (buttons.length !== 2) return `expected 2 pager buttons, saw ${buttons.length}`;
				const prev = buttons[0] as HTMLButtonElement;
				return prev.disabled || 'previous should be disabled on the first page';
			}
		},
		{
			id: 'no-results-state',
			description: 'a matchless query is active but shows the no-results message',
			onlyFixtures: ['no-results'],
			check: ({ contract, root }) =>
				(contract.status === 'empty' &&
					contract.active === 'true' &&
					contract.shown === '0' &&
					(root.textContent ?? '').includes('No recipes match')) ||
				`status=${contract.status} active=${contract.active} shown=${contract.shown}`
		},
		{
			id: 'keyword-pressed',
			description: 'a selected chip is aria-pressed and recorded in the contract',
			onlyFixtures: ['keyword-selected'],
			check: ({ contract, root }) => {
				if (contract.keywords !== 'quick') return `keywords=${contract.keywords}`;
				if (contract.active !== 'true') return `active=${contract.active}`;
				const pressed = [...root.querySelectorAll('.chip')].find(
					(c) => c.getAttribute('aria-pressed') === 'true'
				);
				return pressed?.textContent?.includes('quick') || 'no pressed chip for "quick"';
			}
		},
		{
			id: 'facet-pins-selected',
			description: 'a selected keyword absent from the facets is pinned first and pressed',
			onlyFixtures: ['facet-narrowed'],
			check: ({ contract, root }) => {
				if (contract.chips !== 'quick|weeknight|one-pot') return `chips=${contract.chips}`;
				const all = [...root.querySelectorAll('.chip')];
				const first = all[0];
				if (first?.getAttribute('aria-pressed') !== 'true') return 'pinned chip not pressed';
				if (!first?.textContent?.includes('quick')) return 'first chip is not "quick"';
				const facetPressed = all.slice(1).some((c) => c.getAttribute('aria-pressed') === 'true');
				return !facetPressed || 'a facet chip is pressed but should not be';
			}
		},
		{
			id: 'clears-selection',
			description: 'clicking clear empties the selection and deactivates the keyword filter',
			onlyFixtures: ['clear-selection'],
			check: ({ contract, root }) => {
				if (contract.keywords !== '') return `keywords=${contract.keywords}`;
				const pressed = [...root.querySelectorAll('.chip')].some(
					(c) => c.getAttribute('aria-pressed') === 'true'
				);
				if (pressed) return 'a chip is still pressed after clear';
				return root.querySelector('.clear-kw') === null || 'clear button should disappear';
			}
		},
		{
			id: 'query-echoes',
			description: 'typing updates the query contract and activates the search',
			onlyFixtures: ['type-query'],
			check: ({ contract }) =>
				(contract.query === 'anchovy' && contract.active === 'true') ||
				`query=${contract.query} active=${contract.active}`
		},
		{
			id: 'chip-toggles',
			description: 'clicking the first chip selects "quick" and presses it',
			onlyFixtures: ['toggle-chip'],
			check: ({ contract, root }) => {
				if (contract.keywords !== 'quick') return `keywords=${contract.keywords}`;
				const first = root.querySelector('.chip');
				return first?.getAttribute('aria-pressed') === 'true' || 'first chip not pressed';
			}
		},
		{
			id: 'long-name-rendered',
			description: 'the overlong name renders in full as a single row',
			onlyFixtures: ['long-name'],
			check: ({ root, props }) => {
				const rows = root.querySelectorAll('.rows .row').length;
				if (rows !== 1) return `expected 1 row, saw ${rows}`;
				const name = root.querySelector('.rows .name')?.textContent?.trim() ?? '';
				return name === props.results?.items[0].name || `name not rendered in full: ${name}`;
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
