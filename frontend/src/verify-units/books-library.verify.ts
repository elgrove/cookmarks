import BooksLibrary, { type LibraryBook } from '$lib/components/BooksLibrary.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = { books: LibraryBook[] };

const bookSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	recipeCount: z.number().int().nonnegative(),
	hasCover: z.boolean()
});

// Incoming (recently-added) order is deliberately NOT alphabetical, so a title
// sort visibly reorders the list.
const populated: LibraryBook[] = [
	{ id: 'a1', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 100, hasCover: false },
	{ id: 'a2', title: 'A Modern Way to Eat', author: 'Anna Jones', recipeCount: 200, hasCover: false },
	{ id: 'a3', title: 'The Nordic Baking Book', author: 'Magnus Nilsson', recipeCount: 84, hasCover: true },
	{ id: 'a4', title: 'A Modern Way to Cook', author: 'Anna Jones', recipeCount: 150, hasCover: false },
	{ id: 'a5', title: 'Persiana', author: 'Sabrina Ghayour', recipeCount: 92, hasCover: true }
];

const SEARCH = 'input[type="search"]';
const SORT = 'select[aria-label="Sort books"]';

const unit: VerifiableUnit<Props> = {
	id: 'books-library',
	title: 'Books library',
	description: 'The collection grid with client-side search + sort, recipe-count circles, and no-image plates.',
	kind: 'component',
	component: BooksLibrary,
	propsSchema: z.object({ books: z.array(bookSchema) }),
	fixtures: [
		{ id: 'populated', description: 'several books, default (recently-added) order', props: { books: populated } },
		{ id: 'empty', description: 'no books in the library', props: { books: [] } },
		{
			id: 'pending-extraction',
			description: 'a zero-recipe book shows the pending note, not a count',
			props: {
				books: [
					{ id: 'b1', title: 'River Cottage Veg', author: 'Hugh Fearnley-Whittingstall', recipeCount: 200, hasCover: false },
					{ id: 'b2', title: 'Just added, not yet extracted', author: 'Unknown', recipeCount: 0, hasCover: false }
				]
			}
		},
		{
			id: 'search-match',
			description: 'searching narrows to matching title/author',
			props: { books: populated },
			act: ({ type }) => type(SEARCH, 'modern')
		},
		{
			id: 'sort-title',
			description: 'sorting Title A–Z reorders the visible list',
			props: { books: populated },
			act: ({ type }) => type(SORT, 'title')
		},
		{
			id: 'no-results',
			description: 'probe: a search matching nothing shows the calm empty state',
			probe: true,
			props: { books: populated },
			act: ({ type }) => type(SEARCH, 'zzzznope')
		},
		{
			id: 'long-title',
			description: 'probe: an overlong unicode title must not break layout',
			probe: true,
			props: {
				books: [
					{
						id: 'c1',
						title:
							'A Modern Way to Cook: 150+ Vegetarian Recipes for Quick, Flavour-Packed Meals — Crème Brûlée, Soufflé & Far More Than Will Ever Fit On One Line',
						author: 'Anna Jones',
						recipeCount: 3,
						hasCover: false
					}
				]
			}
		},
		{
			id: 'contract-lie',
			description: 'probe: a deliberately-failing invariant proves the harness reports truthfully',
			probe: true,
			props: { books: populated.slice(0, 2) }
		}
	],
	invariants: [
		{
			id: 'unfiltered-count',
			description: 'with no query the count equals the whole library',
			onlyFixtures: ['populated'],
			check: ({ contract, props }) =>
				(contract.query === '' && Number(contract.count) === props.books.length) ||
				`expected count=${props.books.length} query=empty, saw ${contract.count}/${contract.query}`
		},
		{
			id: 'default-order',
			description: 'the default sort preserves the incoming (recently-added) order',
			onlyFixtures: ['populated'],
			check: ({ contract, props }) =>
				contract.first === props.books[0].title || `first=${contract.first}`
		},
		{
			id: 'empty-state',
			description: 'an empty library flags empty and a zero count',
			onlyFixtures: ['empty'],
			check: ({ contract }) =>
				(contract.empty === 'true' && contract.count === '0') ||
				`expected empty=true count=0, saw empty=${contract.empty} count=${contract.count}`
		},
		{
			id: 'extracted-badges',
			description: 'one count circle per extracted book; none for unextracted',
			onlyFixtures: ['populated', 'pending-extraction'],
			check: ({ root, props }) => {
				const extracted = props.books.filter((b) => b.recipeCount > 0).length;
				const badges = root.querySelectorAll('.count-badge').length;
				return badges === extracted || `expected ${extracted} count circles, saw ${badges}`;
			}
		},
		{
			id: 'pending-no-circle',
			description: 'the unextracted book gets no circle; the extracted one shows its count',
			onlyFixtures: ['pending-extraction'],
			check: ({ contract, root, props }) => {
				const unextracted = props.books.filter((b) => b.recipeCount === 0).length;
				if (Number(contract.pending) !== unextracted) return `pending=${contract.pending}`;
				const badge = root.querySelector('.count-badge')?.textContent?.trim();
				return badge === '200' || `badge text=${badge}`;
			}
		},
		{
			id: 'search-filters',
			description: 'searching "modern" shows only matching books',
			onlyFixtures: ['search-match'],
			check: ({ contract, root }) => {
				if (contract.query !== 'modern') return `query=${contract.query}`;
				if (Number(contract.count) !== 2) return `expected 2 matches, saw ${contract.count}`;
				const titles = [...root.querySelectorAll('.title')].map((t) => (t.textContent ?? '').toLowerCase());
				return titles.every((t) => t.includes('modern')) || `non-matching title rendered: ${titles}`;
			}
		},
		{
			id: 'sort-applied',
			description: 'Title A–Z makes the alphabetically-first book lead',
			onlyFixtures: ['sort-title'],
			check: ({ contract }) =>
				(contract.sort === 'title' && contract.first === 'A Modern Way to Cook') ||
				`saw sort=${contract.sort} first=${contract.first}`
		},
		{
			id: 'no-results-state',
			description: 'a non-matching search shows the calm no-results message',
			onlyFixtures: ['no-results'],
			check: ({ contract, root }) =>
				(Number(contract.count) === 0 &&
					contract.empty === 'true' &&
					(root.textContent ?? '').includes('No books match')) ||
				`count=${contract.count} empty=${contract.empty}`
		},
		{
			id: 'intentional-fail',
			description: 'always fails — the truthfulness probe',
			onlyFixtures: ['contract-lie'],
			check: () => 'intentional failure: this probe must surface as FAIL'
		}
	]
};

export default unit;
