import HomeLanding, {
	type BookOfTheDay,
	type ContinueBook,
	type ReadProgress
} from '$lib/components/HomeLanding.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = {
	bookOfTheDay: BookOfTheDay | null;
	progress?: ReadProgress;
	continueReading?: ContinueBook[];
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
	recipeCount: z.number().int().nonnegative(),
	seenCount: z.number().int().nonnegative(),
	hasCover: z.boolean()
});

const progressSchema = z.object({
	recipes: z.number().int().nonnegative(),
	recipesSeen: z.number().int().nonnegative()
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
		recipeCount: 100,
		seenCount: 37,
		hasCover: false
	},
	{
		id: 'c2',
		title: 'Persiana',
		author: 'Sabrina Ghayour',
		recipeCount: 92,
		seenCount: 4,
		hasCover: true
	}
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
		continueReading: z.array(continueSchema).optional()
	}),
	fixtures: [
		{
			id: 'populated',
			description: 'books part-read lead the page; the feature and read figure follow',
			props: {
				bookOfTheDay: feature,
				progress: { recipes: 13403, recipesSeen: 1204 },
				continueReading: started
			}
		},
		{
			id: 'single-continue',
			description: 'one part-read book still leads, without stretching across the page',
			props: {
				bookOfTheDay: feature,
				progress: { recipes: 13403, recipesSeen: 37 },
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
				progress: { recipes: 13403, recipesSeen: 1204 },
				continueReading: [
					started[0],
					started[1],
					{ ...started[0], id: 'c3', title: 'The Nordic Baking Book', author: 'Magnus Nilsson', recipeCount: 84, seenCount: 80 },
					{ ...started[1], id: 'c4', title: 'A Modern Way to Eat', author: 'Anna Jones', recipeCount: 200, seenCount: 1 }
				]
			}
		},
		{
			id: 'nothing-read',
			description: 'probe: nothing seen yet — no strip, and 0% rather than a divide by zero',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { recipes: 13403, recipesSeen: 0 },
				continueReading: []
			}
		},
		{
			id: 'finished-book-supplied',
			description: 'probe: a fully-read book handed to the strip still renders sanely at 100%',
			probe: true,
			props: {
				bookOfTheDay: feature,
				progress: { recipes: 100, recipesSeen: 100 },
				continueReading: [{ ...started[0], seenCount: 100 }]
			}
		}
	],
	invariants: [
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
							: (props.progress?.recipes ?? 0) > 0
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
				'the library read figure is the seen share rounded and clamped, and absent when there is nothing to read',
			check: ({ contract, root, props }) => {
				const { recipes = 0, recipesSeen = 0 } = props.progress ?? {};
				const shown = contract['read-pct'] ?? '';
				if (recipes === 0) {
					if (shown !== '') return `read-pct=${shown} with an empty library`;
					return (
						root.querySelector('.progress-block') === null ||
						'a read figure is rendered with no recipes'
					);
				}
				const want = Math.max(0, Math.min(100, Math.round((100 * recipesSeen) / recipes)));
				if (Number(shown) !== want) return `read-pct=${shown} expected ${want}`;
				const pct = root.querySelector('.progress-block .pct')?.textContent?.trim();
				return pct === `${want}%` || `figure="${pct}" expected ${want}%`;
			}
		},
		{
			id: 'continue-strip',
			description:
				'the strip renders one book card per supplied book, each linking to its book and stating its own read share',
			check: ({ contract, root, props }) => {
				const books = props.continueReading ?? [];
				if (Number(contract['continue-count']) !== books.length)
					return `continue-count=${contract['continue-count']} expected ${books.length}`;
				const cells = [...root.querySelectorAll('.strip .cell')];
				if (cells.length !== books.length)
					return `rendered ${cells.length} strip cards, expected ${books.length}`;
				for (let i = 0; i < books.length; i++) {
					const book = books[i];
					// Mirrors readPercent, null branch included: no recipes means no percentage.
					const want =
						book.recipeCount === 0
							? 0
							: Math.max(0, Math.min(100, Math.round((100 * book.seenCount) / book.recipeCount)));
					// One nav link per card — the card's own stretched link, no second focus stop.
					const links = cells[i].querySelectorAll('a[href^="/books/"]');
					if (links.length !== 1) return `card ${i} has ${links.length} nav links, expected 1`;
					if (links[0].getAttribute('href') !== `/books/${book.id}`)
						return `card ${i} href=${links[0].getAttribute('href')}`;
					const text = cells[i].textContent ?? '';
					if (!text.includes(`${book.seenCount} of ${book.recipeCount}`))
						return `card ${i} omits its read count: "${text.trim()}"`;
					const width = cells[i].querySelector<HTMLElement>('.progress-fill')?.style.width;
					if (width !== `${want}%`) return `card ${i} fill width=${width} expected ${want}%`;
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
