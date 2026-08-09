import RecipeDetail, { type RecipeDetailData } from '$lib/components/RecipeDetail.svelte';
import { keywordHref } from '$lib/api/recipes';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = { recipe: RecipeDetailData };

const READ_TOGGLE = '.read';

const recipeSchema = z.object({
	id: z.string(),
	bookId: z.string(),
	bookTitle: z.string(),
	bookAuthor: z.string(),
	bookHasCover: z.boolean(),
	name: z.string(),
	description: z.string().nullable(),
	ingredients: z.array(z.string()),
	instructions: z.array(z.string()),
	yields: z.string().nullable(),
	keywords: z.array(z.string()),
	hasImage: z.boolean(),
	isFavourite: z.boolean(),
	context: z.string(),
	contextQuery: z.string(),
	searchHref: z.string().nullable(),
	previous: z.object({ id: z.string(), name: z.string() }).nullable(),
	next: z.object({ id: z.string(), name: z.string() }).nullable()
});

const trofie: RecipeDetailData = {
	id: '7c9e6679-7425-40de-944b-e07fc1f90ae7',
	bookId: 'a0054f3d-3f99-4502-aa48-dc933c13fab8',
	bookTitle: 'Pasta Grannies: The Official Cookbook',
	bookAuthor: 'Vicky Bennison',
	bookHasCover: true,
	name: "Rosetta's Trofie with Basil Sauce",
	description:
		'A Ligurian classic: hand-rolled trofie tossed through a vivid basil pesto pounded by hand. Rosetta has made it this way for sixty years.',
	ingredients: [
		'400g trofie pasta',
		'60g basil leaves',
		'50g pine nuts',
		'2 garlic cloves',
		'120ml extra-virgin olive oil',
		'40g Parmesan, finely grated'
	],
	instructions: [
		'Pound the basil, garlic and pine nuts to a coarse paste.',
		'Work in the cheese, then trickle in the oil until glossy.',
		'Boil the trofie until al dente, reserving a little cooking water.',
		'Toss the pasta through the pesto, loosening with the water.'
	],
	yields: 'Serves 4',
	keywords: ['Pasta', 'Pesto', 'Vegetarian', 'Liguria'],
	hasImage: false,
	isFavourite: false,
	context: 'book',
	contextQuery: 'context=book',
	searchHref: null,
	previous: { id: '11111111-1111-4111-8111-111111111111', name: "Cornelia's Pansotti with Walnut Pesto" },
	next: { id: '22222222-2222-4222-8222-222222222222', name: "Angela's Busiate with Trapanese Pesto" }
};

// >360 chars, so it clamps behind a Read more toggle.
const longDesc =
	'A long-simmered Ligurian classic that rewards patience: trofie hand-rolled on a wooden board, ' +
	'then dressed with a basil pesto pounded by hand in a marble mortar until it turns a vivid, glossy ' +
	'green. Rosetta has made it this way for sixty years, and insists the cheese goes in before the oil, ' +
	'the garlic stays gentle, and a ladle of pasta water does the rest. Serve at once, while the sauce ' +
	'still clings to every twist.';

const unit: VerifiableUnit<Props> = {
	id: 'recipe-detail',
	title: 'Recipe detail',
	description:
		'The reading view: a breadcrumb bar with a prev/next pager, a masthead (title, chips, yield, Read-more description, favourite ★ + add-to-list actions), a two-column ingredients + numbered method body, and book provenance.',
	kind: 'component',
	component: RecipeDetail,
	propsSchema: z.object({ recipe: recipeSchema }),
	fixtures: [
		{
			id: 'populated',
			description: 'a full recipe with description, keywords and yield (no image in source)',
			props: { recipe: trofie }
		},
		{
			id: 'image-in-source',
			description: 'the source carried an image: a bordered figure renders it from the API',
			props: { recipe: { ...trofie, hasImage: true } }
		},
		{
			id: 'no-keywords',
			description: 'no keywords: the chip row is absent and the metadata reads em-dash',
			props: { recipe: { ...trofie, keywords: [] } }
		},
		{
			id: 'minimal',
			description: 'no description or yield: the plate opening falls back to the first step',
			props: {
				recipe: {
					...trofie,
					name: 'Plain Boiled Eggs',
					description: null,
					yields: null,
					keywords: [],
					hasImage: false,
					ingredients: ['4 large eggs'],
					instructions: ['Boil the eggs for 7 minutes.', 'Cool under cold water, then peel.']
				}
			}
		},
		{
			id: 'long-description',
			description: 'a long blurb is clamped behind a Read more control',
			props: { recipe: { ...trofie, description: longDesc } }
		},
		{
			id: 'read-more-expanded',
			description: 'clicking Read more reveals the full blurb and flips the toggle',
			props: { recipe: { ...trofie, description: longDesc } },
			act: ({ click }) => click('.readmore')
		},
		{
			id: 'first-in-source',
			description: 'first recipe in the ordering: only a Next link in the pager',
			props: { recipe: { ...trofie, previous: null } }
		},
		{
			id: 'last-in-source',
			description: 'last recipe in the ordering: only a Previous link in the pager',
			props: { recipe: { ...trofie, next: null } }
		},
		{
			id: 'only-recipe',
			description: 'a lone recipe in its ordering: no pager at all',
			props: { recipe: { ...trofie, previous: null, next: null } }
		},
		{
			id: 'search-context',
			description: 'reached from a search: pager carries the search query; breadcrumb links back to it',
			props: {
				recipe: {
					...trofie,
					context: 'search',
					contextQuery: 'context=search&q=pesto&sort=name',
					searchHref: '/recipes?q=pesto&sort=name'
				}
			}
		},
		{
			id: 'long-content',
			description: 'probe: an overlong unicode title with many ingredients and steps must not break layout',
			probe: true,
			props: {
				recipe: {
					...trofie,
					name: 'Grand-mère’s Slow-Braised Bourguignon with Crème Fraîche, Sauté Mushrooms & Far More Than Will Ever Sit On One Line',
					description:
						'An unhurried Sunday braise — beef cheeks coloured hard, doused in a whole bottle of red, and left to fall apart over an afternoon while the kitchen fills with the smell of bay and thyme and patience.',
					ingredients: Array.from({ length: 14 }, (_, i) => `Ingredient ${i + 1} — a reasonably long descriptive line that keeps going`),
					instructions: Array.from({ length: 12 }, (_, i) => `Step ${i + 1}: a fairly verbose instruction that wraps across more than a single line to test the method gutter.`),
					keywords: ['Beef', 'Braise', 'French', 'Sunday', 'Slow', 'Winter', 'Stew']
				}
			}
		},
		{
			id: 'contract-lie',
			description: 'expectFail: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { recipe: trofie }
		}
	],
	invariants: [
		{
			id: 'contract-id',
			description: 'the data-verify-id contract reports the recipe id',
			check: ({ contract, props }) =>
				contract.id === props.recipe.id || `contract id=${contract.id}, props id=${props.recipe.id}`
		},
		{
			id: 'title',
			description: 'the display heading is the recipe name',
			check: ({ root, props }) => {
				const h1 = root.querySelector('.display')?.textContent?.trim() ?? '';
				return h1 === props.recipe.name || `display="${h1}"`;
			}
		},
		{
			id: 'ingredient-count',
			description: 'rendered ingredient rows match the count contract and the props',
			check: ({ contract, root, props }) => {
				if (Number(contract.ingredients) !== props.recipe.ingredients.length)
					return `contract ingredients=${contract.ingredients} expected ${props.recipe.ingredients.length}`;
				const rows = root.querySelectorAll('.ingredients li').length;
				return rows === props.recipe.ingredients.length || `rendered ${rows} ingredient rows`;
			}
		},
		{
			id: 'method-steps',
			description: 'rendered steps match the count and carry sequential zero-padded numbers',
			check: ({ contract, root, props }) => {
				if (Number(contract.steps) !== props.recipe.instructions.length)
					return `contract steps=${contract.steps} expected ${props.recipe.instructions.length}`;
				const items = [...root.querySelectorAll('.method li')];
				if (items.length !== props.recipe.instructions.length)
					return `rendered ${items.length} steps`;
				const nums = items.map((li) => li.querySelector('.stepno')?.textContent?.trim() ?? '');
				const expected = props.recipe.instructions.map((_, i) => String(i + 1).padStart(2, '0'));
				return nums.join(',') === expected.join(',') || `step numbers=${nums.join(',')}`;
			}
		},
		{
			id: 'keyword-chips',
			description: 'rendered chips equal the keyword-count contract and the props',
			check: ({ contract, root, props }) => {
				if (Number(contract.keywords) !== props.recipe.keywords.length)
					return `contract keywords=${contract.keywords} expected ${props.recipe.keywords.length}`;
				const chips = root.querySelectorAll('.chips .chip').length;
				return chips === props.recipe.keywords.length || `rendered ${chips} chips`;
			}
		},
		{
			id: 'keyword-links',
			description: 'each keyword chip links to the keyword-filtered recipes list',
			onlyFixtures: ['populated'],
			check: ({ root, props }) => {
				const chips = [...root.querySelectorAll('.chips .chip')];
				if (chips.length !== props.recipe.keywords.length)
					return `rendered ${chips.length} chips, expected ${props.recipe.keywords.length}`;
				for (let i = 0; i < chips.length; i++) {
					if (chips[i].tagName !== 'A') return `chip ${i} is <${chips[i].tagName.toLowerCase()}>`;
					const want = keywordHref(props.recipe.keywords[i]);
					const href = chips[i].getAttribute('href');
					if (href !== want) return `chip ${i} href=${href} expected ${want}`;
				}
				return true;
			}
		},
		{
			id: 'description-lede',
			description: 'a description renders as a serif lede; absent when there is none',
			check: ({ root, props }) => {
				const present = root.querySelector('.lede') !== null;
				const expected = !!props.recipe.description?.trim();
				return present === expected || `lede present=${present} expected=${expected}`;
			}
		},
		{
			id: 'read-more-collapsed',
			description: 'a long blurb starts clamped and offers a Read more toggle',
			onlyFixtures: ['long-description'],
			check: ({ root }) => {
				const btn = root.querySelector('.readmore');
				if (!btn) return 'no Read more control';
				if (btn.textContent?.trim() !== 'Read more') return `button text=${btn.textContent?.trim()}`;
				return root.querySelector('.lede.clamped') !== null || 'lede not clamped when collapsed';
			}
		},
		{
			id: 'read-more-expands',
			description: 'clicking the toggle removes the clamp and reads Read less',
			onlyFixtures: ['read-more-expanded'],
			check: ({ root }) => {
				if (root.querySelector('.lede.clamped')) return 'lede still clamped after expand';
				const btn = root.querySelector('.readmore');
				return btn?.textContent?.trim() === 'Read less' || `button text=${btn?.textContent?.trim()}`;
			}
		},
		{
			id: 'image-flag',
			description: 'the data-verify-has-image contract reflects whether the source had an image',
			check: ({ contract, props }) => {
				const flag = props.recipe.hasImage ? 'true' : 'false';
				return (
					contract['has-image'] === flag ||
					`has-image=${contract['has-image']} expected ${flag}`
				);
			}
		},
		{
			id: 'image-figure',
			description:
				'with an image, a bordered figure shows the recipe image from the API (alt set); without one, no figure renders',
			check: ({ root, props }) => {
				const fig = root.querySelector('figure.recipe-figure');
				if (!props.recipe.hasImage)
					return fig === null || 'a no-image recipe rendered an image figure';
				if (!fig) return 'hasImage but no image figure rendered';
				const img = fig.querySelector('img.recipe-image');
				const want = `/api/recipes/${props.recipe.id}/image`;
				if (img?.getAttribute('src') !== want)
					return `figure img src=${img?.getAttribute('src')} expected ${want}`;
				return (img.getAttribute('alt')?.trim().length ?? 0) > 0 || 'recipe image has empty alt';
			}
		},
		{
			id: 'book-link',
			description: 'the page links back to the owning book',
			check: ({ root, props }) =>
				root.querySelector(`a[href="/books/${props.recipe.bookId}"]`) !== null ||
				`no link to /books/${props.recipe.bookId}`
		},
		{
			id: 'pager-context',
			description: 'the data-verify-context contract reflects the navigation ordering',
			check: ({ contract, props }) =>
				contract.context === props.recipe.context ||
				`context=${contract.context} expected ${props.recipe.context}`
		},
		{
			id: 'prev-link',
			description: 'a Previous link appears iff there is a previous recipe, carrying the context query',
			check: ({ root, props }) => {
				const a = root.querySelector('.pager a.prev');
				if (props.recipe.previous) {
					if (!a) return 'previous recipe present but no Prev link';
					const want = `/recipes/${props.recipe.previous.id}?${props.recipe.contextQuery}`;
					return a.getAttribute('href') === want || `prev href=${a.getAttribute('href')} expected ${want}`;
				}
				return a === null || 'Prev link shown with no previous recipe';
			}
		},
		{
			id: 'next-link',
			description: 'a Next link appears iff there is a next recipe, carrying the context query',
			check: ({ root, props }) => {
				const a = root.querySelector('.pager a.next');
				if (props.recipe.next) {
					if (!a) return 'next recipe present but no Next link';
					const want = `/recipes/${props.recipe.next.id}?${props.recipe.contextQuery}`;
					return a.getAttribute('href') === want || `next href=${a.getAttribute('href')} expected ${want}`;
				}
				return a === null || 'Next link shown with no next recipe';
			}
		},
		{
			id: 'search-breadcrumb',
			description: 'a search context shows a breadcrumb that links back to the originating search',
			onlyFixtures: ['search-context'],
			check: ({ root, props }) => {
				const back = root.querySelector(`.crumb a[href="${props.recipe.searchHref}"]`);
				if (!back) return `no breadcrumb link back to ${props.recipe.searchHref}`;
				return (
					(root.querySelector('.crumb')?.textContent ?? '').includes('Search results') ||
					'breadcrumb missing "Search results"'
				);
			}
		},
		{
			id: 'open-in-book-link',
			description: 'the actions row links into the reader at this recipe, contract-matched and named',
			check: ({ root, contract, props }) => {
				const want = `/books/${props.recipe.bookId}/read?at=${props.recipe.id}`;
				if (contract['open-in-book'] !== want)
					return `contract open-in-book=${contract['open-in-book']} expected ${want}`;
				const a = root.querySelector('a.open-in-book');
				if (!a) return 'no open-in-book link in the actions row';
				if (a.getAttribute('href') !== want)
					return `href=${a.getAttribute('href')} expected ${want}`;
				const name = a.getAttribute('aria-label')?.trim() ?? a.textContent?.trim() ?? '';
				return name.length > 0 || 'open-in-book link has no accessible name';
			}
		},
		{
			id: 'no-recipe-read-state',
			description:
				'a recipe carries no read state of its own — reading is a property of books now',
			check: ({ root, contract }) => {
				if (root.querySelector(READ_TOGGLE)) return 'a read toggle survives on the recipe page';
				return contract.seen === undefined || `a seen contract survives: ${contract.seen}`;
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
