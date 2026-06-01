import BookDetail, { type BookDetailData } from '$lib/components/BookDetail.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = { book: BookDetailData };

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
	hasCover: z.boolean(),
	added: z.string().nullable(),
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
	hasCover: true,
	added: '2025-05-22T20:56:10Z',
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
			description: 'a book with nothing extracted: empty state, no count circle',
			props: {
				book: {
					...pastaGrannies,
					recipeCount: 0,
					recipes: [],
					hasCover: false
				}
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
					recipeCount: 3
				}
			}
		},
		{
			id: 'long-title',
			description: 'probe: an overlong title + many keywords must not break layout',
			probe: true,
			props: {
				book: {
					...pastaGrannies,
					title:
						'A Very Long Cookbook Title That Goes On: With An Equally Unreasonable Subtitle That Should Wrap Gracefully Across Several Lines Without Breaking',
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
			id: 'intentional-fail',
			description: 'always fails — the truthfulness sentinel (expectFail)',
			onlyFixtures: ['contract-lie'],
			check: () => 'intentional failure: this sentinel must surface as FAIL'
		}
	]
};

export default unit;
