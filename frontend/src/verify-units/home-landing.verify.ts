import HomeLanding, {
	type BookOfTheDay,
	type ContinueBook,
	type ReadProgress,
	type RecentRecipe
} from '$lib/components/HomeLanding.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = {
	bookOfTheDay: BookOfTheDay | null;
	progress?: ReadProgress;
	continueReading?: ContinueBook[];
	recentlyRead?: RecentRecipe[];
};

const bookSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	description: z.string(),
	recipeCount: z.number().int().nonnegative(),
	hasCover: z.boolean()
});

const continueSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	mode: z.enum(['book', 'recipes']),
	fraction: z.number().min(0).max(1),
	resumeRecipeId: z.string().nullable(),
	hasCover: z.boolean()
});

const recentSchema = z.object({
	id: z.string(),
	name: z.string(),
	bookId: z.string(),
	bookTitle: z.string()
});

const progressSchema = z.object({
	books: z.number().int().nonnegative(),
	booksRead: z.number().int().nonnegative()
});

const feature: BookOfTheDay = {
	id: 'd1',
	title: "A Cook's Book",
	author: 'Nigel Slater',
	description:
		'The story of Nigel Slater’s life in recipes — from the first jam tart to the kitchen he cooks in now, gathered as a warm, unhurried record of a life lived through food.',
	recipeCount: 220,
	hasCover: false
};

const started: ContinueBook[] = [
	{
		id: 'c1',
		title: 'Salt, Fat, Acid, Heat',
		author: 'Samin Nosrat',
		mode: 'book',
		fraction: 0.37,
		resumeRecipeId: 'r1',
		hasCover: false
	},
	{
		id: 'c2',
		title: 'Persiana',
		author: 'Sabrina Ghayour',
		mode: 'recipes',
		fraction: 0.04,
		resumeRecipeId: 'r9',
		hasCover: true
	}
];

const recent: RecentRecipe[] = [
	{
		id: 'r1',
		name: 'Buttermilk-Marinated Roast Chicken',
		bookId: 'c1',
		bookTitle: 'Salt, Fat, Acid, Heat: Mastering the Elements of Good Cooking'
	},
	{ id: 'r2', name: 'Shirazi Salad', bookId: 'c2', bookTitle: 'Persiana' },
	{ id: 'r3', name: 'Tahdig', bookId: 'c2', bookTitle: 'Persiana' }
];

const unit: VerifiableUnit<Props> = {
	id: 'home-landing',
	title: 'Home landing',
	description:
		'The quiet landing, led by the books you are part-way through; the book-of-the-day feature and the library read figure follow it.',
	kind: 'component',
	component: HomeLanding,
	propsSchema: z.object({
		bookOfTheDay: bookSchema.nullable(),
		progress: progressSchema.optional(),
		continueReading: z.array(continueSchema).optional(),
		recentlyRead: z.array(recentSchema).optional()
	}),
	fixtures: [
		{
			id: 'populated',
			description: 'books part-read lead the page; the feature and read figure follow',
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 24 },
				continueReading: started,
				recentlyRead: recent
			}
		},
		{
			id: 'recent-only',
			description:
				'probe: recipes read across finished books — a recent index with no strip to lead',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 24 },
				continueReading: [],
				recentlyRead: recent
			}
		},
		{
			id: 'long-recent-name',
			description: 'probe: an overlong recipe and book title in the recent index must not break',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 24 },
				continueReading: [],
				recentlyRead: [
					{
						id: 'rx',
						name: 'Grand-mère’s Slow-Braised Bourguignon with Crème Fraîche, Sauté Mushrooms & Rather More Title Than Any One Line Will Hold',
						bookId: 'c1',
						bookTitle:
							'An Unreasonably Long Cookbook Title: With A Subtitle That Also Refuses To Stop'
					}
				]
			}
		},
		{
			id: 'single-continue',
			description: 'one part-read book still leads, without stretching across the page',
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 1 },
				continueReading: [started[0]]
			}
		},
		{
			id: 'no-feature',
			description: 'probe: an empty library shows the calm empty state, no feature',
			probe: true,
			props: { bookOfTheDay: null }
		},
		{
			id: 'full-strip',
			description: 'probe: the strip at its backend cap of four books',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 24 },
				continueReading: [
					started[0],
					started[1],
					{ ...started[0], id: 'c3', title: 'The Nordic Baking Book', author: 'Magnus Nilsson', fraction: 0.95 },
					{ ...started[1], id: 'c4', title: 'A Modern Way to Eat', author: 'Anna Jones', fraction: 0.005 }
				]
			}
		},
		{
			id: 'nothing-read',
			description: 'probe: nothing seen yet — no strip, and 0% rather than a divide by zero',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 0 },
				continueReading: []
			}
		},
		{
			id: 'just-opened',
			description: 'probe: a book opened but not yet moved through — 0%, no rule to draw',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { books: 192, booksRead: 0 },
				continueReading: [{ ...started[0], fraction: 0 }]
			}
		},
		{
			id: 'finished-book-supplied',
			description: 'probe: a fully-read book handed to the strip still renders sanely at 100%',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { books: 12, booksRead: 12 },
				continueReading: [{ ...started[0], fraction: 1 }]
			}
		}
	],
	invariants: [
		{
			id: 'recent-index',
			description:
				'the recent index lists each recipe read, numbered, linking to the recipe and its book',
			check: ({ contract, root, props }) => {
				const items = props.recentlyRead ?? [];
				if (Number(contract['recent-count']) !== items.length)
					return `recent-count=${contract['recent-count']} expected ${items.length}`;
				const rows = [...root.querySelectorAll('.recent-index li')];
				if (rows.length !== items.length) return `${rows.length} rows for ${items.length} recipes`;
				if (!items.length)
					return root.querySelector('.recent') === null || 'a recent section with nothing in it';
				for (const [i, row] of rows.entries()) {
					const recipe = row.querySelector('.rtitle');
					const want = `/recipes/${items[i].id}`;
					if (recipe?.getAttribute('href') !== want)
						return `row ${i} recipe href=${recipe?.getAttribute('href')} expected ${want}`;
					if ((recipe.textContent ?? '').trim() !== items[i].name)
						return `row ${i} name="${(recipe.textContent ?? '').trim()}"`;
					const book = row.querySelector('.rbook');
					const wantBook = `/books/${items[i].bookId}`;
					if (book?.getAttribute('href') !== wantBook)
						return `row ${i} book href=${book?.getAttribute('href')} expected ${wantBook}`;
				}
				return true;
			}
		},
		{
			id: 'feature-consistency',
			description: 'the feature renders exactly when a book of the day is supplied',
			check: ({ contract, root, props }) => {
				const flag = contract['has-feature'] === 'true';
				const present = !!root.querySelector('.feature');
				if (flag !== (props.bookOfTheDay !== null)) return `has-feature=${contract['has-feature']}`;
				if (flag !== present) return 'has-feature flag disagrees with the rendered DOM';
				return true;
			}
		},
		{
			id: 'continue-leads',
			description:
				'books part-read lead the page and own the h1; the feature and the library figure come after them, in that order',
			check: ({ contract, root, props }) => {
				const books = props.continueReading ?? [];
				const want = books.length ? 'continue' : props.bookOfTheDay ? 'feature' : 'empty';
				if (contract.lead !== want) return `lead=${contract.lead} expected ${want}`;

				const order = [...root.querySelectorAll('.continue, .feature, .progress-block')].map(
					(el) => el.className.split(' ')[0]
				);
				const expected = ['continue', 'feature', 'progress-block'].filter((cls) =>
					cls === 'continue'
						? books.length > 0
						: cls === 'feature'
							? props.bookOfTheDay !== null
							: (props.progress?.books ?? 0) > 0
				);
				if (order.join('|') !== expected.join('|'))
					return `section order=${order.join('|')} expected ${expected.join('|')}`;

				// An empty library states itself in prose and has no section to head.
				if (want === 'empty')
					return (
						root.querySelector('h1') === null || 'an h1 is rendered with nothing to show'
					);

				// Otherwise exactly one h1, on whichever section leads.
				const h1s = [...root.querySelectorAll('h1')];
				if (h1s.length !== 1) return `${h1s.length} h1 elements, expected 1`;
				const heading = (h1s[0].textContent ?? '').trim();
				if (want === 'continue')
					return heading === 'Continue reading' || `h1="${heading}" expected the strip masthead`;
				return (
					heading === (props.bookOfTheDay ? props.bookOfTheDay.title.split(':')[0].trim() : '') ||
					`h1="${heading}" expected the feature title`
				);
			}
		},
		{
			id: 'title-rendered',
			description: 'when present, the book title appears in the DOM',
			onlyFixtures: ['populated'],
			check: ({ root, props }) =>
				(props.bookOfTheDay !== null &&
					(root.textContent ?? '').includes(props.bookOfTheDay.title)) ||
				'book title not rendered'
		},
		{
			id: 'read-percentage',
			description:
				'the library read figure is the share of books read through, rounded and clamped, and absent for an empty library',
			check: ({ contract, root, props }) => {
				const { books = 0, booksRead = 0 } = props.progress ?? {};
				const shown = contract['read-pct'] ?? '';
				if (books === 0) {
					if (shown !== '') return `read-pct=${shown} with an empty library`;
					return (
						root.querySelector('.progress-block') === null ||
						'a read figure is rendered with no books'
					);
				}
				const want = Math.max(0, Math.min(100, Math.round((100 * booksRead) / books)));
				if (Number(shown) !== want) return `read-pct=${shown} expected ${want}`;
				const pct = root.querySelector('.progress-block .pct')?.textContent?.trim();
				return pct === `${want}%` || `figure="${pct}" expected ${want}%`;
			}
		},
		{
			id: 'continue-strip',
			description:
				'the strip renders one book card per supplied book, each leading back into the reader and stating how far through it is',
			check: ({ contract, root, props }) => {
				const books = props.continueReading ?? [];
				if (Number(contract['continue-count']) !== books.length)
					return `continue-count=${contract['continue-count']} expected ${books.length}`;
				const cells = [...root.querySelectorAll('.strip .cell')];
				if (cells.length !== books.length)
					return `rendered ${cells.length} strip cards, expected ${books.length}`;
				for (let i = 0; i < books.length; i++) {
					const book = books[i];
					const want = Math.round(book.fraction * 100);
					// One nav link per card — the card's own stretched link, no second focus stop.
					const links = cells[i].querySelectorAll('a[href]');
					if (links.length !== 1) return `card ${i} has ${links.length} nav links, expected 1`;
					// Continuing resumes the mode the book was left in, never the book page.
					const wantHref =
						book.mode === 'recipes' && book.resumeRecipeId
							? `/recipes/${book.resumeRecipeId}?context=book`
							: `/books/${book.id}/read`;
					if (links[0].getAttribute('href') !== wantHref)
						return `card ${i} href=${links[0].getAttribute('href')} expected ${wantHref}`;
					const text = cells[i].textContent ?? '';
					if (!text.includes(`${want}% through`))
						return `card ${i} omits how far through it is: "${text.trim()}"`;
					// A book only just opened has nothing to draw, so it carries no rule at all.
					const width = cells[i].querySelector<HTMLElement>('.progress-fill')?.style.width;
					const wantWidth = want === 0 ? undefined : `${want}%`;
					if (width !== wantWidth) return `card ${i} fill width=${width} expected ${wantWidth}`;
					// The meta line states the count in words, so the card's clay circle is off.
					if (cells[i].querySelector('.count-badge'))
						return `card ${i} shows a count circle beside the written count`;
				}
				return true;
			}
		}
	]
};

export default unit;
