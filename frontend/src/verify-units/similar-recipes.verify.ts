import SimilarRecipes, { type SimilarRecipesProps } from '$lib/components/SimilarRecipes.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = SimilarRecipesProps;

const rowSchema = z.object({
	id: z.string(),
	name: z.string(),
	bookId: z.string(),
	bookTitle: z.string(),
	bookAuthor: z.string(),
	keywords: z.array(z.string())
});

const propsSchema = z.object({
	recipes: z.array(rowSchema),
	basis: z.enum(['vector', 'keyword']),
	moreHref: z.string().optional()
});

const neighbours: Props['recipes'] = [
	{
		id: '7c9e6679-7425-40de-944b-e07fc1f90ae7',
		name: 'Coconut Dal with Tempered Spices',
		bookId: 'a0054f3d-3f99-4502-aa48-dc933c13fab8',
		bookTitle: 'Made in India',
		bookAuthor: 'Meera Sodha',
		keywords: ['Lentil', 'Vegan', 'Curry']
	},
	{
		id: '11111111-1111-4111-8111-111111111111',
		name: 'Red Lentil & Squash Soup',
		bookId: 'b1165g4e-4g00-5613-bb59-ed044f24g406',
		bookTitle: 'Simple',
		bookAuthor: 'Yotam Ottolenghi',
		keywords: ['Soup', 'Lentil', 'Warming']
	},
	{
		id: '22222222-2222-4222-8222-222222222222',
		name: 'Spiced Chickpeas with Yoghurt',
		bookId: 'c2276h5f-5h11-6724-cc60-fe155g35h517',
		bookTitle: 'A Modern Way to Cook',
		bookAuthor: 'Anna Jones',
		keywords: ['Chickpea', 'Spiced']
	}
];

const unit: VerifiableUnit<Props> = {
	id: 'similar-recipes',
	title: 'Similar recipes',
	description:
		'The footer section on a recipe page: a mono "Similar recipes" heading over a list of related-recipe rows (name · book · author · keywords), each linking to that recipe. Populated from the embedding nearest-neighbours, with a shared-keyword fallback; a designed empty state when there are none.',
	kind: 'component',
	component: SimilarRecipes,
	propsSchema,
	fixtures: [
		{
			id: 'vector',
			description: 'the usual case: embedding neighbours, several rows with keywords',
			props: { recipes: neighbours, basis: 'vector' }
		},
		{
			id: 'keyword-fallback',
			description: 'the recipe had no embedding: neighbours found by shared keywords',
			props: { recipes: neighbours.slice(0, 2), basis: 'keyword' }
		},
		{
			id: 'single',
			description: 'probe: a lone neighbour must still render as a proper list',
			probe: true,
			props: { recipes: neighbours.slice(0, 1), basis: 'vector' }
		},
		{
			id: 'long-content',
			description: 'probe: overlong unicode names and many keywords must not break the rows',
			probe: true,
			props: {
				recipes: neighbours.map((r, i) => ({
					...r,
					name: `Grand-mère’s Slow-Braised ${'Cassoulet '.repeat(6)}No.${i + 1}`,
					bookAuthor: 'A Cook With A Remarkably Long Compound Surname-Hyphenation',
					keywords: ['Beef', 'Braise', 'French', 'Sunday', 'Slow', 'Winter', 'Stew']
				})),
				basis: 'vector'
			}
		},
		{
			id: 'with-more-link',
			description: 'the recipe-page footer: a "More like this" link to the fuller list',
			props: {
				recipes: neighbours,
				basis: 'vector',
				moreHref: '/recipes?similar=7c9e6679-7425-40de-944b-e07fc1f90ae7'
			}
		},
		{
			id: 'empty',
			description: 'no neighbours found: the designed empty state, not a bare heading',
			props: { recipes: [], basis: 'keyword' }
		},
		{
			id: 'with-picker',
			description: 'the row picker switched on: every row carries the labelled [+] trigger',
			props: { recipes: neighbours, basis: 'vector', listPicker: {} }
		}
	],
	invariants: [
		{
			id: 'count-contract',
			description: 'the data-verify-count contract equals the number of neighbours',
			check: ({ contract, props }) =>
				contract.count === String(props.recipes.length) ||
				`contract count=${contract.count} expected ${props.recipes.length}`
		},
		{
			id: 'basis-contract',
			description: 'the data-verify-basis contract reports how the neighbours were found',
			check: ({ contract, props }) =>
				contract.basis === props.basis ||
				`contract basis=${contract.basis} expected ${props.basis}`
		},
		{
			id: 'heading',
			description: 'the section carries the "Similar recipes" mono heading',
			check: ({ root }) => {
				const h = root.querySelector('.label')?.textContent?.trim() ?? '';
				return h === 'Similar recipes' || `heading="${h}"`;
			}
		},
		{
			id: 'row-count',
			description: 'rendered rows match the neighbour count',
			check: ({ root, props }) => {
				const rows = root.querySelectorAll('.rows .row').length;
				return rows === props.recipes.length || `rendered ${rows} rows`;
			}
		},
		{
			id: 'row-links',
			description: 'every neighbour links to its recipe page',
			check: ({ root, props }) => {
				for (const r of props.recipes) {
					if (!root.querySelector(`a[href="/recipes/${r.id}"]`))
						return `no link to /recipes/${r.id}`;
				}
				return true;
			}
		},
		{
			id: 'empty-state',
			description: 'with no neighbours, a worded empty state shows and no list renders',
			onlyFixtures: ['empty'],
			check: ({ root }) => {
				if (root.querySelector('.rows')) return 'list rendered for an empty result';
				return root.querySelector('.empty') !== null || 'no empty-state message';
			}
		},
		{
			id: 'picker-on-rows',
			description: 'with listPicker set, every row renders the per-row [+] trigger',
			onlyFixtures: ['with-picker'],
			check: ({ root, props }) => {
				const triggers = root.querySelectorAll('.rows .row .add-trigger').length;
				return (
					triggers === props.recipes.length ||
					`${triggers} pickers for ${props.recipes.length} rows`
				);
			}
		},
		{
			id: 'more-link',
			description: 'a "more like this" link appears iff a moreHref is provided (and there are rows)',
			check: ({ root, props }) => {
				const a = root.querySelector('a.more');
				const expected = !!props.moreHref && props.recipes.length > 0;
				if (expected) {
					if (!a) return 'expected a more-link but none rendered';
					return a.getAttribute('href') === props.moreHref || `more href=${a.getAttribute('href')}`;
				}
				return a === null || 'more-link rendered without a moreHref';
			}
		}
	]
};

export default unit;
