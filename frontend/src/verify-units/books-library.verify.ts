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

const withCards = ['populated', 'pending-extraction', 'long-title', 'contract-lie'];

const populated: LibraryBook[] = [
	{ id: 'a1', title: 'A Modern Way to Cook', author: 'Anna Jones', recipeCount: 150, hasCover: true },
	{ id: 'a2', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 100, hasCover: false },
	{ id: 'a3', title: 'The Nordic Baking Book', author: 'Magnus Nilsson', recipeCount: 84, hasCover: true },
	{ id: 'a4', title: 'Persiana', author: 'Sabrina Ghayour', recipeCount: 92, hasCover: false },
	{ id: 'a5', title: "A Cook's Book", author: 'Nigel Slater', recipeCount: 220, hasCover: true }
];

const unit: VerifiableUnit<Props> = {
	id: 'books-library',
	title: 'Books library',
	description: 'The collection grid: book cards, accession numbers, recipe counts, no-image plates.',
	kind: 'component',
	component: BooksLibrary,
	propsSchema: z.object({ books: z.array(bookSchema) }),
	fixtures: [
		{ id: 'populated', description: 'several books with varied recipe counts', props: { books: populated } },
		{ id: 'empty', description: 'no books in the library', props: { books: [] } },
		{
			id: 'pending-extraction',
			description: 'a book with zero recipes shows the pending note, not a count',
			props: {
				books: [
					{ id: 'b1', title: 'River Cottage Veg', author: 'Hugh Fearnley-Whittingstall', recipeCount: 200, hasCover: false },
					{ id: 'b2', title: 'Just added, not yet extracted', author: 'Unknown', recipeCount: 0, hasCover: false }
				]
			}
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
			id: 'count-matches',
			description: 'the rendered count equals the number of books passed in',
			check: ({ contract, props }) =>
				Number(contract.count) === props.books.length ||
				`expected count=${props.books.length}, saw ${contract.count}`
		},
		{
			id: 'empty-state',
			description: 'the empty fixture flags empty and a zero count',
			onlyFixtures: ['empty'],
			check: ({ contract }) =>
				(contract.empty === 'true' && contract.count === '0') ||
				`expected empty=true count=0, saw empty=${contract.empty} count=${contract.count}`
		},
		{
			id: 'pending-rendered',
			description: 'zero-recipe books report as pending, both in the contract and the DOM',
			onlyFixtures: ['pending-extraction'],
			check: ({ contract, root }) =>
				(Number(contract.pending) >= 1 && (root.textContent ?? '').includes('pending extraction')) ||
				`expected a pending note; pending=${contract.pending}`
		},
		{
			id: 'accession-present',
			description: 'cards carry a CM-NNN accession number',
			onlyFixtures: withCards,
			check: ({ root }) =>
				/CM-\d{3}/.test(root.querySelector('.accession')?.textContent ?? '') ||
				'first card is missing a CM-NNN accession'
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
