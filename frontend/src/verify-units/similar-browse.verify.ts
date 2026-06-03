import SimilarBrowse, { type SimilarBrowseData } from '$lib/components/SimilarBrowse.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = SimilarBrowseData;

const rowSchema = z.object({
	id: z.string(),
	name: z.string(),
	bookId: z.string(),
	bookTitle: z.string(),
	bookAuthor: z.string(),
	keywords: z.array(z.string())
});

const propsSchema = z.object({
	recipeId: z.string(),
	recipeName: z.string(),
	recipes: z.array(rowSchema),
	basis: z.enum(['vector', 'keyword'])
});

const SOURCE_ID = 'f519ae42-e06c-4c52-a1bd-ec1e087a67d1';

const neighbours: Props['recipes'] = [
	{
		id: '7c9e6679-7425-40de-944b-e07fc1f90ae7',
		name: 'Chicken Karaage',
		bookId: 'a0054f3d-3f99-4502-aa48-dc933c13fab8',
		bookTitle: 'JapanEasy: Classic and Modern Japanese Recipes',
		bookAuthor: 'Tim Anderson',
		keywords: ['Fried Chicken', 'Japanese']
	},
	{
		id: '11111111-1111-4111-8111-111111111111',
		name: 'Karaage (Japanese Fried Chicken)',
		bookId: 'b1165g4e-4g00-5613-bb59-ed044f24g406',
		bookTitle: 'Japanese Food Made Easy',
		bookAuthor: 'Aya Nishimura',
		keywords: ['Fried Chicken', 'Quick']
	},
	{
		id: '22222222-2222-4222-8222-222222222222',
		name: 'Tatsuta-age',
		bookId: 'c2276h5f-5h11-6724-cc60-fe155g35h517',
		bookTitle: 'Japanese Soul Cooking',
		bookAuthor: 'Tadashi Ono',
		keywords: ['Deep Fry', 'Japanese']
	}
];

const base: Props = {
	recipeId: SOURCE_ID,
	recipeName: 'Kara-age',
	recipes: neighbours,
	basis: 'vector'
};

const unit: VerifiableUnit<Props> = {
	id: 'similar-browse',
	title: 'Similar browse',
	description:
		'The "/recipes?similar=<id>" view: a breadcrumb (Recipes › the recipe › Similar), a serif "Similar to <recipe>" heading, and the full ranked list of similar recipes as index rows. A designed empty state when none are found.',
	kind: 'component',
	component: SimilarBrowse,
	propsSchema,
	fixtures: [
		{
			id: 'populated',
			description: 'the usual case: a recipe name and its ranked similar list',
			props: base
		},
		{
			id: 'single',
			description: 'probe: a lone neighbour still renders heading, breadcrumb and one row',
			probe: true,
			props: { ...base, recipes: neighbours.slice(0, 1) }
		},
		{
			id: 'long-name',
			description: 'probe: an overlong unicode source name must not break the heading/crumb',
			probe: true,
			props: {
				...base,
				recipeName:
					'Grand-mère’s Slow-Braised Cassoulet with Crème Fraîche & Far More Than Sits On One Line'
			}
		},
		{
			id: 'empty',
			description: 'no neighbours: the designed empty state under the heading',
			props: { ...base, recipes: [] }
		}
	],
	invariants: [
		{
			id: 'count-contract',
			description: 'the data-verify-count contract equals the number of rows',
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
			id: 'heading-names-source',
			description: 'the heading names the source recipe',
			check: ({ root, props }) => {
				const h = root.querySelector('.display')?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
				return h.includes(props.recipeName) || `heading="${h}"`;
			}
		},
		{
			id: 'back-link',
			description: 'the breadcrumb links back to the source recipe',
			check: ({ root, props }) =>
				root.querySelector(`.crumb a[href="/recipes/${props.recipeId}"]`) !== null ||
				`no breadcrumb link to /recipes/${props.recipeId}`
		},
		{
			id: 'row-links',
			description: 'every similar recipe links to its recipe page',
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
		}
	]
};

export default unit;
