import HomeLanding, {
	type BookOfTheDay,
	type ContinueBook
} from '$lib/components/HomeLanding.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = {
	bookOfTheDay: BookOfTheDay | null;
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
	mode: z.enum(['book', 'recipes']),
	fraction: z.number().min(0).max(1),
	resumeRecipeId: z.string().nullable(),
	hasCover: z.boolean()
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

const unit: VerifiableUnit<Props> = {
	id: 'home-landing',
	title: 'Home landing',
	description:
		'The quiet landing, led by the book of the day, with the Continue Reading shelf beneath it.',
	kind: 'component',
	component: HomeLanding,
	propsSchema: z.object({
		bookOfTheDay: bookSchema.nullable(),
		continueReading: z.array(continueSchema).optional()
	}),
	fixtures: [
		{
			id: 'populated',
			description: 'the book of the day leads, followed by the Continue Reading shelf',
			props: {
				bookOfTheDay: feature,
				continueReading: started
			}
		},
		{
			id: 'single-continue',
			description: 'one part-read book follows the feature without stretching across the page',
			props: {
				bookOfTheDay: feature,
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
				continueReading: []
			}
		},
		{
			id: 'just-opened',
			description: 'probe: a book opened but not yet moved through — 0%, no rule to draw',
			probe: true,
			props: {
				bookOfTheDay: feature,
				continueReading: [{ ...started[0], fraction: 0 }]
			}
		},
		{
			id: 'finished-book-supplied',
			description: 'probe: a fully-read book handed to the strip still renders sanely at 100%',
			probe: true,
			props: {
				bookOfTheDay: feature,
				continueReading: [{ ...started[0], fraction: 1 }]
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
				'the book of the day leads the page, with Continue Reading beneath it',
			check: ({ contract, root, props }) => {
				const books = props.continueReading ?? [];
				const want = props.bookOfTheDay ? 'feature' : books.length ? 'continue' : 'empty';
				if (contract.lead !== want) return `lead=${contract.lead} expected ${want}`;

				const order = [...root.querySelectorAll('.feature, .continue')].map(
					(el) => el.className.split(' ')[0]
				);
				const expected = ['feature', 'continue'].filter((cls) =>
					cls === 'continue'
						? books.length > 0
						: props.bookOfTheDay !== null
				);
				if (order.join('|') !== expected.join('|'))
					return `section order=${order.join('|')} expected ${expected.join('|')}`;

				// An empty library states itself in prose and has no section to head.
				if (want === 'empty')
					return (
						root.querySelector('h1') === null || 'an h1 is rendered with nothing to show'
					);

				// Otherwise exactly one h1, on the leading section.
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
			id: 'home-surface-sections',
			description: 'the home surface omits the removed Up next, Recently opened, and Read so far sections',
			check: ({ root }) => {
				if (!['.upnext', '.recent', '.progress-block'].every((selector) => !root.querySelector(selector)))
					return 'the home surface renders a removed secondary section';
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
			id: 'continue-strip',
			description:
				'the strip renders one book card per supplied book, with separate resume and book-page links',
			check: ({ contract, root, props }) => {
				const books = props.continueReading ?? [];
				if (Number(contract['continue-count']) !== books.length)
					return `continue-count=${contract['continue-count']} expected ${books.length}`;
				// Scoped to the continue section — the Up next shelf shares the strip classes.
				const cells = [...root.querySelectorAll('.continue .cell')];
				if (cells.length !== books.length)
					return `rendered ${cells.length} strip cards, expected ${books.length}`;
				for (let i = 0; i < books.length; i++) {
					const book = books[i];
					const want = Math.round(book.fraction * 100);
					// The cover resumes reading while the metadata opens the book page.
					const links = cells[i].querySelectorAll('a[href]');
					if (links.length !== 2) return `card ${i} has ${links.length} nav links, expected 2`;
					const wantHref =
						book.mode === 'recipes' && book.resumeRecipeId
							? `/recipes/${book.resumeRecipeId}?context=book`
							: `/books/${book.id}/read`;
					const cover = cells[i].querySelector('.cover-link');
					if (cover?.getAttribute('href') !== wantHref)
						return `card ${i} cover href=${cover?.getAttribute('href')} expected ${wantHref}`;
					const meta = cells[i].querySelector('.meta-link');
					const bookHref = `/books/${book.id}`;
					if (meta?.getAttribute('href') !== bookHref)
						return `card ${i} metadata href=${meta?.getAttribute('href')} expected ${bookHref}`;
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
