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
		'The quiet landing: a book-of-the-day feature, the library read figure, and a strip of books part-read.',
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
			description: 'a book of the day with a description',
			props: {
				bookOfTheDay: feature,
				progress: { recipes: 13403, recipesSeen: 1204 },
				continueReading: started
			}
		},
		{
			id: 'no-feature',
			description: 'probe: an empty library shows the calm empty state, no feature',
			probe: true,
			props: { bookOfTheDay: null }
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
				'the strip renders one linked row per supplied book, each carrying its own read share',
			check: ({ contract, root, props }) => {
				const books = props.continueReading ?? [];
				if (Number(contract['continue-count']) !== books.length)
					return `continue-count=${contract['continue-count']} expected ${books.length}`;
				const rows = [...root.querySelectorAll('.strip li')];
				if (rows.length !== books.length)
					return `rendered ${rows.length} strip rows, expected ${books.length}`;
				for (let i = 0; i < books.length; i++) {
					const book = books[i];
					// Mirrors readPercent, null branch included: no recipes means no percentage.
					const want =
						book.recipeCount === 0
							? 0
							: Math.max(0, Math.min(100, Math.round((100 * book.seenCount) / book.recipeCount)));
					const href = rows[i].querySelector('a')?.getAttribute('href');
					if (href !== `/books/${book.id}`) return `row ${i} href=${href}`;
					const text = rows[i].textContent ?? '';
					if (!text.includes(`${book.seenCount} of ${book.recipeCount}`))
						return `row ${i} omits its read count: "${text.trim()}"`;
					const width = rows[i].querySelector<HTMLElement>('.rule-fill')?.style.width;
					if (width !== `${want}%`) return `row ${i} fill width=${width} expected ${want}%`;
				}
				return true;
			}
		}
	]
};

export default unit;
