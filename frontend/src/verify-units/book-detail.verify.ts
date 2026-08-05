import BookDetail, { type BookDetailData } from '$lib/components/BookDetail.svelte';
import { keywordHref } from '$lib/api/recipes';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = { book: BookDetailData; onDelete?: (opts: { exclude: boolean }) => void };

const DELETE_BTN = '.delete-btn';
const CONFIRM_DELETE = '.confirm-delete';
const EXCLUDE = '.exclude input';

const recipeSchema = z.object({
	id: z.string(),
	name: z.string(),
	keywords: z.array(z.string())
});

const bookSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	isbn: z.string().nullable(),
	pubdate: z.string().nullable(),
	description: z.string(),
	recipeCount: z.number().int().nonnegative(),
	seenCount: z.number().int().nonnegative(),
	hasCover: z.boolean(),
	hasEpub: z.boolean(),
	added: z.string().nullable(),
	keywords: z.array(z.string()),
	recipes: z.array(recipeSchema)
});

function recipes(n: number): BookDetailData['recipes'] {
	const names = [
		"Rosetta's Trofie with Basil Sauce",
		"Maurizio's Pesto alla Genovese",
		"Cornelia's Pansotti with Walnut Pesto",
		"Angela's Busiate with Trapanese Pesto",
		"Margherita's Cavati with Spring Vegetables",
		"Giuseppina's Pici with Garlic Tomato Sauce",
		"Laura's Pizzoccheri from Valtellina",
		"Ada's Taglioli and Bean Soup",
		"Maria's Chickpea and Pasta Soup",
		"Olga's Canederli"
	];
	const kw = [['Pasta', 'Sauce', 'Quick'], ['Pesto', 'Vegetarian'], ['Ravioli'], ['Soup', 'Beans']];
	return Array.from({ length: n }, (_, i) => ({
		id: `r${i}`,
		name: names[i % names.length],
		keywords: kw[i % kw.length]
	}));
}

const pastaGrannies: BookDetailData = {
	id: 'a0054f3d-3f99-4502-aa48-dc933c13fab8',
	title: "Pasta Grannies: The Official Cookbook: The Secrets of Italy's Best Home Cooks",
	author: 'Vicky Bennison',
	isbn: '9781784883096',
	pubdate: '2019-10-17',
	description:
		'Learn how to make pasta like Italian nonnas do. Inspired by the hugely popular YouTube channel of the same name, Pasta Grannies is a collection of time-perfected Italian recipes from the people who have spent a lifetime cooking for love, not a living: Italian grandmothers. Featuring easy, accessible recipes from all over Italy, you will be transported into the very heart of the Italian home.',
	recipeCount: 49,
	seenCount: 12,
	hasCover: true,
	hasEpub: true,
	added: '2025-05-22T20:56:10Z',
	keywords: ['Italian', 'Pasta', 'Regional', 'Traditional'],
	recipes: recipes(10)
};

const unit: VerifiableUnit<Props> = {
	id: 'book-detail',
	title: 'Book detail',
	description:
		'A single book: masthead + description, a sticky cover/metadata/actions sidebar, and a numbered index of a random sample of its recipes.',
	kind: 'component',
	component: BookDetail,
	propsSchema: z.object({ book: bookSchema }),
	fixtures: [
		{
			id: 'populated',
			description: 'a book with a cover and 10 sampled recipes (of 49)',
			props: { book: pastaGrannies }
		},
		{
			id: 'no-cover',
			description: 'a book without a cover falls back to the §7 title plate',
			props: { book: { ...pastaGrannies, hasCover: false } }
		},
		{
			id: 'no-recipes',
			description: 'a book with nothing extracted: empty state, no count circle, no tags',
			props: {
				book: {
					...pastaGrannies,
					recipeCount: 0,
					seenCount: 0,
					recipes: [],
					hasCover: false,
					keywords: []
				}
			}
		},
		{
			id: 'unseen',
			description: 'a book nothing has been read from yet reads 0%',
			props: { book: { ...pastaGrannies, seenCount: 0 } }
		},
		{
			id: 'fully-read',
			description: 'every recipe seen reads 100%',
			props: { book: { ...pastaGrannies, seenCount: 49 } }
		},
		{
			id: 'seen-over-count',
			description:
				'probe: a stale seen count above the total clamps to 100%, never overflows',
			probe: true,
			props: { book: { ...pastaGrannies, seenCount: 80 } }
		},
		{
			id: 'unextracted-progress',
			description: 'probe: nothing extracted → no percentage at all, never NaN',
			probe: true,
			props: {
				book: { ...pastaGrannies, recipeCount: 0, seenCount: 4, recipes: [], keywords: [] }
			}
		},
		{
			id: 'no-subtitle',
			description: 'a plain title (no colon) renders without a subtitle line',
			props: {
				book: {
					...pastaGrannies,
					title: 'Persiana',
					isbn: null,
					added: null,
					recipes: recipes(3),
					recipeCount: 3,
					seenCount: 1
				}
			}
		},
		{
			id: 'no-epub',
			description: 'a book with no EPUB on disk offers no "Read epub" action',
			props: { book: { ...pastaGrannies, hasEpub: false } }
		},
		{
			id: 'long-title',
			description: 'probe: an overlong title + many book and recipe keywords must not break layout',
			probe: true,
			props: {
				book: {
					...pastaGrannies,
					title:
						'A Very Long Cookbook Title That Goes On: With An Equally Unreasonable Subtitle That Should Wrap Gracefully Across Several Lines Without Breaking',
					keywords: [
						'Italian',
						'Pasta',
						'Regional',
						'Traditional',
						'Vegetarian',
						'Slow Cooking',
						'Mediterranean',
						'Comfort Food',
						'Family',
						'Rustic'
					],
					recipes: [
						{
							id: 'rx',
							name: 'A recipe with an unusually long descriptive name that keeps going and going past one line',
							keywords: ['Pasta', 'Vegetarian', 'Quick', 'Sauce', 'Tuscany', 'Soup', 'Beans', 'Pesto']
						}
					],
					recipeCount: 49
				}
			}
		},
		{
			id: 'delete-confirm',
			description: 'the delete action opens a confirm step with the exclusion box unticked',
			props: { book: pastaGrannies, onDelete: () => {} },
			act: ({ click }) => click(DELETE_BTN)
		},
		{
			id: 'delete-plain',
			description: 'confirming without ticking the box deletes but records no exclusion',
			props: { book: pastaGrannies, onDelete: () => {} },
			act: ({ click }) => {
				click(DELETE_BTN);
				click(CONFIRM_DELETE);
			}
		},
		{
			id: 'delete-excluded',
			description: 'ticking the box before confirming deletes and excludes from future syncs',
			props: { book: pastaGrannies, onDelete: () => {} },
			act: ({ click }) => {
				click(DELETE_BTN);
				click(EXCLUDE);
				click(CONFIRM_DELETE);
			}
		},
		{
			id: 'delete-confirm-empty-book',
			description: 'probe: confirming on a zero-recipe book omits the recipe-loss warning',
			probe: true,
			props: {
				book: { ...pastaGrannies, recipeCount: 0, seenCount: 0, recipes: [], keywords: [] },
				onDelete: () => {}
			},
			act: ({ click }) => click(DELETE_BTN)
		},
		{
			id: 'contract-lie',
			description: 'expectFail: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { book: pastaGrannies }
		}
	],
	invariants: [
		{
			id: 'contract-id',
			description: 'the data-verify-id contract reports the book id',
			check: ({ contract, props }) =>
				contract.id === props.book.id || `contract id=${contract.id}, props id=${props.book.id}`
		},
		{
			id: 'recipe-count',
			description: 'the contract recipe-count matches the total',
			check: ({ contract, props }) =>
				Number(contract['recipe-count']) === props.book.recipeCount ||
				`count=${contract['recipe-count']} expected ${props.book.recipeCount}`
		},
		{
			id: 'read-percentage',
			description:
				'read % is the seen share rounded and clamped to 0–100, and absent entirely when nothing is extracted',
			check: ({ contract, root, props }) => {
				const { seenCount, recipeCount } = props.book;
				if (Number(contract['seen-count']) !== seenCount)
					return `seen-count=${contract['seen-count']} expected ${seenCount}`;
				const shown = contract['read-pct'] ?? '';
				const row = [...root.querySelectorAll('dl.meta div')].find(
					(d) => d.querySelector('dt')?.textContent?.trim() === 'Read'
				);
				if (recipeCount === 0) {
					if (shown !== '') return `read-pct=${shown} for an unextracted book`;
					return row === undefined || 'a read row is rendered with nothing extracted';
				}
				const want = Math.max(0, Math.min(100, Math.round((100 * seenCount) / recipeCount)));
				if (Number(shown) !== want) return `read-pct=${shown} expected ${want}`;
				if (!row) return 'no read row rendered';
				return (
					(row.textContent ?? '').includes(`${want}%`) ||
					`read row text="${(row.textContent ?? '').trim()}"`
				);
			}
		},
		{
			id: 'book-keywords',
			description: 'book-level keyword chips render — one per keyword — and match the contract count',
			check: ({ contract, root, props }) => {
				const want = props.book.keywords.length;
				if (Number(contract.keywords) !== want)
					return `contract keywords=${contract.keywords} expected ${want}`;
				const chips = root.querySelectorAll('.book-tags li').length;
				return chips === want || `rendered ${chips} book-keyword chips, expected ${want}`;
			}
		},
		{
			id: 'keyword-links',
			description: 'book-level and recipe-index keyword chips link to the keyword-filtered recipes list',
			onlyFixtures: ['populated'],
			check: ({ root, props }) => {
				const tags = [...root.querySelectorAll('.book-tags a.chip')];
				if (tags.length !== props.book.keywords.length)
					return `${tags.length} book-keyword links, expected ${props.book.keywords.length}`;
				for (let i = 0; i < tags.length; i++) {
					const want = keywordHref(props.book.keywords[i]);
					if (tags[i].getAttribute('href') !== want)
						return `book tag ${i} href=${tags[i].getAttribute('href')} expected ${want}`;
				}
				const first = props.book.recipes.find((r) => r.keywords.length);
				const chip = root.querySelector('.index a.chip');
				if (first && !chip) return 'no recipe-index keyword link rendered';
				if (first && chip) {
					const want = keywordHref(first.keywords[0]);
					if (chip.getAttribute('href') !== want)
						return `recipe chip href=${chip.getAttribute('href')} expected ${want}`;
				}
				return true;
			}
		},
		{
			id: 'rows-match-shown',
			description: 'rendered recipe rows equal the shown contract and never exceed 10',
			check: ({ contract, root }) => {
				const rows = root.querySelectorAll('.index li').length;
				if (rows > 10) return `rendered ${rows} rows, exceeds 10`;
				return Number(contract.shown) === rows || `shown=${contract.shown} rows=${rows}`;
			}
		},
		{
			id: 'main-title',
			description: 'the pre-colon main title is rendered as the display heading',
			onlyFixtures: ['populated', 'no-cover', 'no-subtitle'],
			check: ({ root, props }) => {
				const main = props.book.title.split(':')[0].trim();
				const h1 = root.querySelector('.display')?.textContent?.trim() ?? '';
				return h1 === main || `display="${h1}" expected "${main}"`;
			}
		},
		{
			id: 'empty-state',
			description: 'a zero-recipe book flags empty, shows no count circle, and the calm message',
			onlyFixtures: ['no-recipes'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.count-badge')) return 'count circle shown for 0 recipes';
				return (
					(root.textContent ?? '').includes('No recipes extracted yet') || 'empty message missing'
				);
			}
		},
		{
			id: 'count-circle-when-extracted',
			description: 'an extracted book shows exactly one count circle bearing the total',
			onlyFixtures: ['populated'],
			check: ({ root, props }) => {
				const badge = root.querySelector('.count-badge')?.textContent?.trim();
				return badge === String(props.book.recipeCount) || `badge=${badge}`;
			}
		},
		{
			id: 'no-subtitle-hidden',
			description: 'a colon-free title renders no subtitle element',
			onlyFixtures: ['no-subtitle'],
			check: ({ root }) =>
				root.querySelector('.subtitle') === null || 'subtitle rendered for a plain title'
		},
		{
			id: 'read-epub-link',
			description: 'a book with an EPUB offers a "Read epub" action linking to its reader',
			onlyFixtures: ['populated', 'no-cover', 'no-subtitle', 'long-title'],
			check: ({ root, contract, props }) => {
				if (contract['has-epub'] !== 'true') return `has-epub contract=${contract['has-epub']}`;
				const href = root.querySelector('a.read-epub')?.getAttribute('href');
				const want = `/books/${props.book.id}/read`;
				return href === want || `read-epub href=${href} expected ${want}`;
			}
		},
		{
			id: 'read-epub-hidden',
			description: 'a book without an EPUB shows no "Read epub" action',
			onlyFixtures: ['no-epub'],
			check: ({ root, contract }) => {
				if (contract['has-epub'] !== 'false') return `has-epub contract=${contract['has-epub']}`;
				return root.querySelector('a.read-epub') === null || 'read-epub link shown without an epub';
			}
		},
		{
			id: 'browse-link',
			description: 'an extracted book links to its recipes, book-filtered and in book order',
			onlyFixtures: ['populated', 'no-cover', 'no-subtitle', 'long-title'],
			check: ({ root, props }) => {
				const href = root.querySelector('a.browse')?.getAttribute('href');
				const want = `/recipes?book_id=${props.book.id}&sort=book`;
				return href === want || `browse href=${href} expected ${want}`;
			}
		},
		{
			id: 'browse-hidden-when-empty',
			description: 'a zero-recipe book offers no browse link',
			onlyFixtures: ['no-recipes'],
			check: ({ root }) =>
				root.querySelector('a.browse') === null || 'browse link shown for an empty book'
		},
		{
			id: 'delete-needs-confirm',
			description: 'delete is a two-step action: no confirm panel until the action is clicked',
			onlyFixtures: ['populated', 'no-cover', 'no-recipes'],
			check: ({ contract, root }) => {
				if (contract['delete-mode'] !== undefined && contract['delete-mode'] !== 'view')
					return `delete-mode=${contract['delete-mode']} before any click`;
				return root.querySelector(CONFIRM_DELETE) === null || 'confirm shown without a click';
			}
		},
		{
			id: 'delete-confirm-step',
			description: 'the confirm step exposes a labelled exclusion box, unticked by default',
			onlyFixtures: ['delete-confirm', 'delete-confirm-empty-book'],
			check: ({ contract, root }) => {
				if (contract['delete-mode'] !== 'confirm') return `delete-mode=${contract['delete-mode']}`;
				if (contract['delete-exclude'] !== 'false')
					return `delete-exclude=${contract['delete-exclude']} — must default off`;
				if (!root.querySelector(CONFIRM_DELETE)) return 'confirm button missing';
				const box = root.querySelector<HTMLInputElement>(EXCLUDE);
				if (!box) return 'exclusion checkbox missing';
				if (box.checked) return 'exclusion checkbox pre-ticked';
				return (
					(box.closest('label')?.textContent ?? '').includes('Calibre') ||
					'exclusion checkbox is not labelled'
				);
			}
		},
		{
			id: 'delete-warns-about-recipes',
			description: 'the confirm names the recipes at stake, and says nothing of them when there are none',
			onlyFixtures: ['delete-confirm', 'delete-confirm-empty-book'],
			check: ({ root, props }) => {
				const prompt = root.querySelector('.confirm .prompt')?.textContent ?? '';
				if (!prompt.includes('Delete this book?')) return `prompt="${prompt.trim()}"`;
				const mentions = prompt.includes(String(props.book.recipeCount));
				if (props.book.recipeCount === 0)
					return !prompt.includes('recipe') || `empty book warns about recipes: "${prompt.trim()}"`;
				return mentions || `prompt omits the recipe count: "${prompt.trim()}"`;
			}
		},
		{
			id: 'delete-fires-handler',
			description: 'confirming fires the delete handler with the exclusion choice, and closes the panel',
			onlyFixtures: ['delete-plain', 'delete-excluded'],
			check: ({ contract, fixture }) => {
				const want = fixture.id === 'delete-excluded' ? 'exclude' : 'plain';
				if (contract.deleted !== want) return `deleted=${contract.deleted} expected ${want}`;
				return contract['delete-mode'] === 'view' || `delete-mode=${contract['delete-mode']}`;
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
