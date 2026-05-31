import HomeLanding, { type BookOfTheDay } from '$lib/components/HomeLanding.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = { bookOfTheDay: BookOfTheDay | null };

const bookSchema = z.object({
	id: z.string(),
	title: z.string(),
	author: z.string(),
	description: z.string(),
	recipeCount: z.number().int().nonnegative(),
	hasCover: z.boolean()
});

const unit: VerifiableUnit<Props> = {
	id: 'home-landing',
	title: 'Home landing',
	description: 'The quiet landing: a single book-of-the-day feature.',
	kind: 'component',
	component: HomeLanding,
	propsSchema: z.object({ bookOfTheDay: bookSchema.nullable() }),
	fixtures: [
		{
			id: 'populated',
			description: 'a book of the day with a description',
			props: {
				bookOfTheDay: {
					id: 'd1',
					title: "A Cook's Book",
					author: 'Nigel Slater',
					description:
						'The story of Nigel Slater’s life in recipes — from the first jam tart to the kitchen he cooks in now, gathered as a warm, unhurried record of a life lived through food.',
					recipeCount: 220,
					hasCover: false
				}
			}
		},
		{
			id: 'no-feature',
			description: 'probe: an empty library shows the calm empty state, no feature',
			probe: true,
			props: { bookOfTheDay: null }
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
		}
	]
};

export default unit;
