import BooksLibrary, { type LibraryBook } from '$lib/components/BooksLibrary.svelte';
import { keywordHref } from '$lib/api/recipes';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = { books: LibraryBook[] };

const bookSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	recipeCount: z.number().int().nonnegative(),
	hasCover: z.boolean(),
	keywords: z.array(z.string()).optional()
});

// Incoming (recently-added) order is deliberately NOT alphabetical, so a title
// sort visibly reorders the list. Keyword counts vary (one over the 3-chip cap, one
// with none) so the card chip behaviour is exercised across the grid.
const populated: LibraryBook[] = [
	{ id: 'a1', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 100, hasCover: false, keywords: ['Fundamentals', 'Technique', 'Mediterranean', 'Reference'] },
	{ id: 'a2', title: 'A Modern Way to Eat', author: 'Anna Jones', recipeCount: 200, hasCover: false, keywords: ['Vegetarian', 'Weeknight'] },
	{ id: 'a3', title: 'The Nordic Baking Book', author: 'Magnus Nilsson', recipeCount: 84, hasCover: true, keywords: ['Baking', 'Nordic', 'Bread'] },
	{ id: 'a4', title: 'A Modern Way to Cook', author: 'Anna Jones', recipeCount: 150, hasCover: false, keywords: [] },
	{ id: 'a5', title: 'Persiana', author: 'Sabrina Ghayour', recipeCount: 92, hasCover: true, keywords: ['Persian', 'Middle Eastern', 'Mezze'] }
];

const SEARCH = 'input[type="search"]';
const SORT = 'select[aria-label="Sort books"]';
const EXTRACTED = '.extracted-checkbox';

// A deliberate mix of extracted (recipeCount > 0) and unextracted (recipeCount === 0)
// books, so the "Extracted only" filter visibly drops the pending ones.
const mixed: LibraryBook[] = [
	{ id: 'm1', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 100, hasCover: false },
	{ id: 'm2', title: 'Just added, not yet extracted', author: 'Unknown', recipeCount: 0, hasCover: false },
	{ id: 'm3', title: 'Persiana', author: 'Sabrina Ghayour', recipeCount: 92, hasCover: true },
	{ id: 'm4', title: 'Another pending import', author: 'Unknown', recipeCount: 0, hasCover: false }
];

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
			description: 'a search matching nothing shows the calm empty state',
			props: { books: populated },
			act: ({ type }) => type(SEARCH, 'zzzznope')
		},
		{
			id: 'long-title',
			description:
				'probe: an overlong unicode clean name renders in full while the colon-subtitle is dropped',
			probe: true,
			props: {
				books: [
					{
						id: 'c1',
						title:
							'A Modern Way to Cook — Crème Brûlée, Soufflé & Far More Than Will Ever Fit On One Line of a Compact Cookbook Card: 150+ Vegetarian Recipes for Quick, Flavour-Packed Meals',
						author: 'Anna Jones',
						recipeCount: 3,
						hasCover: false
					}
				]
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { books: populated.slice(0, 2) }
		},
		{
			id: 'extracted-only-mixed',
			description: 'a mix of extracted and unextracted books, "Extracted only" left unchecked',
			props: { books: mixed }
		},
		{
			id: 'extracted-only-on',
			description: 'ticking "Extracted only" drops the zero-recipe (pending) books',
			props: { books: mixed },
			act: ({ click }) => click(EXTRACTED)
		},
		{
			id: 'extracted-only-empty',
			description: 'probe: "Extracted only" with no extracted books shows the calm empty state',
			probe: true,
			props: {
				books: [
					{ id: 'p1', title: 'Pending import one', author: 'Unknown', recipeCount: 0, hasCover: false },
					{ id: 'p2', title: 'Pending import two', author: 'Unknown', recipeCount: 0, hasCover: false }
				]
			},
			act: ({ click }) => click(EXTRACTED)
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
			id: 'whole-card-clickable',
			description:
				'each book card exposes exactly one stretched nav link to its detail page (whole surface clickable)',
			onlyFixtures: ['populated'],
			check: ({ root }) => {
				const cards = [...root.querySelectorAll('.card')];
				for (const card of cards) {
					const links = card.querySelectorAll('a[href^="/books/"]');
					if (links.length !== 1)
						return `card has ${links.length} nav link(s), expected exactly 1`;
					const href = links[0].getAttribute('href') ?? '';
					if (!/^\/books\/.+/.test(href)) return `nav href not a book detail page: ${href}`;
				}
				return true;
			}
		},
		{
			id: 'card-keyword-chips',
			description: 'each card shows up to three book-keyword chips, in incoming order',
			onlyFixtures: ['populated'],
			check: ({ root, props }) => {
				const cards = [...root.querySelectorAll('.card')];
				if (cards.length !== props.books.length)
					return `rendered ${cards.length} cards, expected ${props.books.length}`;
				for (let i = 0; i < cards.length; i++) {
					const expected = Math.min(3, props.books[i].keywords?.length ?? 0);
					const chips = cards[i].querySelectorAll('.chips .chip').length;
					if (chips !== expected) return `card ${i} shows ${chips} chips, expected ${expected}`;
				}
				return true;
			}
		},
		{
			id: 'card-keyword-links',
			description: 'card keyword chips are links to the keyword-filtered recipes list',
			onlyFixtures: ['populated'],
			check: ({ root, props }) => {
				const cards = [...root.querySelectorAll('.card')];
				for (let i = 0; i < cards.length; i++) {
					const shown = (props.books[i].keywords ?? []).slice(0, 3);
					const links = [...cards[i].querySelectorAll('.chips a.chip')];
					if (links.length !== shown.length)
						return `card ${i}: ${links.length} keyword links, expected ${shown.length}`;
					for (let j = 0; j < shown.length; j++) {
						const want = keywordHref(shown[j]);
						if (links[j].getAttribute('href') !== want)
							return `card ${i} chip ${j} href=${links[j].getAttribute('href')} expected ${want}`;
					}
				}
				return true;
			}
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
			id: 'long-title-rendered',
			description:
				'the card shows the overlong clean name in full (subtitle dropped, no crash/truncation)',
			onlyFixtures: ['long-title'],
			check: ({ root, props }) => {
				const cards = root.querySelectorAll('.card').length;
				if (cards !== props.books.length) return `expected ${props.books.length} card(s), saw ${cards}`;
				const expected = props.books[0].title.split(':')[0].trim();
				const title = root.querySelector('.title')?.textContent?.trim() ?? '';
				return title === expected || `expected clean name "${expected}", saw "${title}"`;
			}
		},
		{
			id: 'intentional-fail',
			description: 'always fails — the truthfulness sentinel (expectFail)',
			onlyFixtures: ['contract-lie'],
			check: () => 'intentional failure: this sentinel must surface as FAIL'
		},
		{
			id: 'extracted-only-off-shows-all',
			description: 'with the filter off the whole mixed library renders and the contract reads off',
			onlyFixtures: ['extracted-only-mixed'],
			check: ({ contract, props }) =>
				(contract['extracted-only'] === 'false' && Number(contract.count) === props.books.length) ||
				`expected extracted-only=false count=${props.books.length}, saw ${contract['extracted-only']}/${contract.count}`
		},
		{
			id: 'extracted-only-filters',
			description: 'ticking the filter renders only books with recipeCount > 0',
			onlyFixtures: ['extracted-only-on'],
			check: ({ contract, root, props }) => {
				const extracted = props.books.filter((b) => b.recipeCount > 0).length;
				if (contract['extracted-only'] !== 'true') return `extracted-only=${contract['extracted-only']}`;
				if (Number(contract.count) !== extracted) return `expected ${extracted} extracted, saw ${contract.count}`;
				const badges = root.querySelectorAll('.count-badge').length;
				return badges === extracted || `expected ${extracted} count circles, saw ${badges}`;
			}
		},
		{
			id: 'extracted-only-empty-state',
			description: 'the filter with no extracted books flags empty and a zero count',
			onlyFixtures: ['extracted-only-empty'],
			check: ({ contract, root }) =>
				(contract['extracted-only'] === 'true' &&
					contract.empty === 'true' &&
					Number(contract.count) === 0 &&
					(root.textContent ?? '').includes('No extracted books yet')) ||
				`extracted-only=${contract['extracted-only']} empty=${contract.empty} count=${contract.count}`
		}
	]
};

export default unit;
