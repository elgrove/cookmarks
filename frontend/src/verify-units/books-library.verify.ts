import BooksLibrary, {
	type BooksLibraryProps,
	type LibraryBook
} from '$lib/components/BooksLibrary.svelte';
import { bookGridDensitySchema } from '$lib/api/auth';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = BooksLibraryProps;

const bookSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	recipeCount: z.number().int().nonnegative(),
	progress: z.number().min(0).max(1).nullable().optional(),
	hasCover: z.boolean(),
	keywords: z.array(z.string()).optional(),
	queuePosition: z.number().int().positive().nullable().optional()
});

// Incoming (recently-added) order is deliberately NOT alphabetical, so a title
// sort visibly reorders the list. Keyword counts vary (one over the 3-chip cap, one
// with none) so the card chip behaviour is exercised across the grid. Seen counts
// mix started, untouched and finished books, so progress rules appear on some cards
// and not others.
const populated: LibraryBook[] = [
	{ id: 'a1', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 100, progress: 0.37, hasCover: false, keywords: ['Fundamentals', 'Technique', 'Mediterranean', 'Reference'] },
	{ id: 'a2', title: 'A Modern Way to Eat', author: 'Anna Jones', recipeCount: 200, progress: 0, hasCover: false, keywords: ['Vegetarian', 'Weeknight'] },
	{ id: 'a3', title: 'The Nordic Baking Book', author: 'Magnus Nilsson', recipeCount: 84, progress: 1, hasCover: true, keywords: ['Baking', 'Nordic', 'Bread'] },
	{ id: 'a4', title: 'A Modern Way to Cook', author: 'Anna Jones', recipeCount: 150, hasCover: false, keywords: [] },
	{ id: 'a5', title: 'Persiana', author: 'Sabrina Ghayour', recipeCount: 92, progress: 0.05, hasCover: true, keywords: ['Persian', 'Middle Eastern', 'Mezze'] }
];

const SEARCH = 'input[type="search"]';
const SORT = 'select[aria-label="Sort books"]';
const EXTRACTED = '.extracted-checkbox';

// A deliberate mix of extracted (recipeCount > 0) and unextracted (recipeCount === 0)
// books, so the "Extracted only" filter visibly drops the pending ones.
const mixed: LibraryBook[] = [
	{ id: 'm1', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 100, progress: 0.12, hasCover: false },
	// An unextracted book that was somehow opened: no recipes to be part-way through.
	{ id: 'm2', title: 'Just added, not yet extracted', author: 'Unknown', recipeCount: 0, progress: 0, hasCover: false },
	{ id: 'm3', title: 'Persiana', author: 'Sabrina Ghayour', recipeCount: 92, progress: null, hasCover: true },
	{ id: 'm4', title: 'Another pending import', author: 'Unknown', recipeCount: 0, hasCover: false }
];

const unit: VerifiableUnit<Props> = {
	id: 'books-library',
	title: 'Books library',
	description: 'The collection grid with client-side search + sort, recipe-count circles, and no-image plates.',
	kind: 'component',
	component: BooksLibrary,
	propsSchema: z.object({
		books: z.array(bookSchema),
		density: bookGridDensitySchema.optional()
	}),
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
			id: 'sort-queue',
			description: 'Queue order leads with the queued books; the rest keep recent order',
			props: {
				// Persiana is 2nd on the queue, Nordic Baking 1st; the other three unqueued.
				books: populated.map((b) =>
					b.id === 'a3'
						? { ...b, queuePosition: 1 }
						: b.id === 'a5'
							? { ...b, queuePosition: 2 }
							: b
				)
			},
			act: ({ type }) => type(SORT, 'queue')
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
		},
		{
			id: 'keyword-filter',
			description: 'clicking a keyword chip narrows the grid to books carrying it',
			props: { books: populated },
			act: ({ click }) => click('.keywords .chip[data-kw="Baking"]')
		},
		{
			id: 'density-sparse',
			description: 'sparse density renders with fewer columns',
			props: { books: populated, density: 'sparse' }
		},
		{
			id: 'density-compact',
			description: 'compact density renders with more columns',
			props: { books: populated, density: 'compact' }
		},
		{
			id: 'density-menu-open',
			description: 'clicking density trigger opens the SVG graphic options menu',
			props: { books: populated, density: 'standard' },
			act: ({ click }) => click('.density-trigger')
		},
		{
			id: 'density-change',
			description: 'clicking compact density option switches density',
			props: { books: populated, density: 'standard' },
			act: async ({ click }) => {
				await click('.density-trigger');
				await click('.density-option[data-density="compact"]');
			}
		},
		{
			id: 'density-probe',
			description: 'probe: opening dropdown and switching density updates active selection',
			probe: true,
			props: { books: populated, density: 'sparse' },
			act: async ({ click }) => {
				await click('.density-trigger');
				await click('.density-option[data-density="compact"]');
			}
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
			id: 'keyword-bar-chips',
			description: 'the keyword filter bar offers one chip per distinct book keyword',
			onlyFixtures: ['populated'],
			check: ({ contract, props }) => {
				const distinct = new Set(props.books.flatMap((b) => b.keywords ?? []));
				const shown = contract['kw-chips'] ? contract['kw-chips'].split('|') : [];
				if (shown.length !== distinct.size)
					return `bar shows ${shown.length} chips, expected ${distinct.size}`;
				return shown.every((c) => distinct.has(c)) || `unexpected chip in bar: ${shown.join('|')}`;
			}
		},
		{
			id: 'keyword-filter-narrows',
			description: 'selecting a keyword filters the grid to books that carry it',
			onlyFixtures: ['keyword-filter'],
			check: ({ contract, root, props }) => {
				if (contract['kw-selected'] !== 'Baking') return `kw-selected=${contract['kw-selected']}`;
				const expected = props.books.filter((b) => (b.keywords ?? []).includes('Baking')).length;
				if (Number(contract.count) !== expected)
					return `expected ${expected} book(s), saw ${contract.count}`;
				const cards = root.querySelectorAll('.card').length;
				return cards === expected || `rendered ${cards} cards, expected ${expected}`;
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
			id: 'progress-rules',
			description:
				'one progress rule per started book — none for untouched ones — and each fill matches how far through it is',
			onlyFixtures: ['populated', 'extracted-only-mixed'],
			check: ({ contract, root, props }) => {
				const started = props.books.filter((b) => (b.progress ?? 0) > 0);
				if (Number(contract['progress-count']) !== started.length)
					return `progress-count=${contract['progress-count']} expected ${started.length}`;
				const rules = [...root.querySelectorAll('.progress')];
				if (rules.length !== started.length)
					return `rendered ${rules.length} progress rules, expected ${started.length}`;
				// The grid renders in the fixture's order, so rules and started books align.
				for (let i = 0; i < started.length; i++) {
					const book = started[i];
					const want = Math.max(
						0,
						Math.min(100, Math.round(100 * (book.progress ?? 0)))
					);
					const width = rules[i].querySelector<HTMLElement>('.progress-fill')?.style.width;
					if (width !== `${want}%`) return `${book.title}: fill width=${width} expected ${want}%`;
				}
				return true;
			}
		},
		{
			id: 'progress-in-link-label',
			description:
				'a started book folds how far through it is into the card link name rather than adding a second focus stop',
			onlyFixtures: ['populated'],
			check: ({ root, props }) => {
				const started = props.books.find((b) => (b.progress ?? 0) > 0);
				if (!started) return 'fixture has no started book';
				const link = root.querySelector(`a[href="/books/${started.id}"]`);
				const label = link?.getAttribute('aria-label') ?? '';
				return (
					label.includes(`${Math.round(100 * (started.progress ?? 0))}% read`) ||
					`link label="${label}"`
				);
			}
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
			id: 'queue-sort-applied',
			description: 'Queue order puts queue position 1 first, then 2, then the unqueued in recent order',
			onlyFixtures: ['sort-queue'],
			check: ({ contract, root, props }) => {
				if (contract.sort !== 'queue') return `sort=${contract.sort}`;
				if (contract.first !== 'The Nordic Baking Book') return `first=${contract.first}`;
				const titles = [...root.querySelectorAll('.meta .title')].map((el) =>
					(el.textContent ?? '').trim()
				);
				const want = ['The Nordic Baking Book', 'Persiana'].concat(
					props.books.filter((b) => !b.queuePosition).map((b) => b.title)
				);
				return (
					titles.slice(0, want.length).join('|') === want.join('|') ||
					`order=${titles.join('|')}`
				);
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
		},
		{
			id: 'default-density',
			description: 'default density is standard and reflects on contract',
			onlyFixtures: ['populated'],
			check: ({ contract }) =>
				contract.density === 'standard' || `expected density=standard, saw ${contract.density}`
		},
		{
			id: 'sparse-density',
			description: 'sparse density fixture reflects on contract and grid data attribute',
			onlyFixtures: ['density-sparse'],
			check: ({ contract, root }) => {
				if (contract.density !== 'sparse') return `contract density=${contract.density}`;
				const grid = root.querySelector('.grid');
				return (
					grid?.getAttribute('data-density') === 'sparse' ||
					`grid data-density=${grid?.getAttribute('data-density')}`
				);
			}
		},
		{
			id: 'compact-density',
			description: 'compact density fixture reflects on contract and grid data attribute',
			onlyFixtures: ['density-compact'],
			check: ({ contract, root }) => {
				if (contract.density !== 'compact') return `contract density=${contract.density}`;
				const grid = root.querySelector('.grid');
				return (
					grid?.getAttribute('data-density') === 'compact' ||
					`grid data-density=${grid?.getAttribute('data-density')}`
				);
			}
		},
		{
			id: 'density-click-switches',
			description: 'clicking compact option updates contract and applies compact grid layout',
			onlyFixtures: ['density-change'],
			check: ({ contract, root }) => {
				if (contract.density !== 'compact') return `contract density=${contract.density}`;
				const grid = root.querySelector('.grid');
				return (
					grid?.getAttribute('data-density') === 'compact' ||
					`grid data-density=${grid?.getAttribute('data-density')}`
				);
			}
		},
		{
			id: 'density-menu-renders-options',
			description: 'open density menu renders all 3 SVG options',
			onlyFixtures: ['density-menu-open'],
			check: ({ root }) => {
				const options = root.querySelectorAll('.density-option');
				return options.length === 3 || `expected 3 density options, saw ${options.length}`;
			}
		},
		{
			id: 'density-probe-invariants',
			description: 'density probe leaves compact state active and applied',
			onlyFixtures: ['density-probe'],
			check: ({ contract, root }) => {
				if (contract.density !== 'compact') return `contract density=${contract.density}`;
				const grid = root.querySelector('.grid');
				return (
					grid?.getAttribute('data-density') === 'compact' ||
					`grid data-density=${grid?.getAttribute('data-density')}`
				);
			}
		}
	]
};

export default unit;
